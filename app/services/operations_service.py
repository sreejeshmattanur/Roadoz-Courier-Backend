import math
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.franchise import Franchise
from app.models.operations import CashVoucher, Expense, Manifest, ManifestOrder, PodRecord, StaffAttendance
from app.models.order import Order, OrderStatus
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.operations import (
    AttendanceCreate,
    AttendanceOut,
    CashVoucherCreate,
    CashVoucherOut,
    ExpenseCreate,
    ExpenseOut,
    ManifestCreate,
    ManifestOut,
    PodCreate,
    PodOut,
)


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id))
    role = row.scalar_one_or_none()
    return role.lower() if role else None


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    franchise = (await db.execute(select(Franchise).where(Franchise.user_id == user.id))).scalar_one_or_none()
    return franchise.id if franchise else None


async def _scope_franchise_id(db: AsyncSession, current_user: User, franchise_id: str | None) -> str | None:
    own_franchise_id = await _resolve_franchise_id(db, current_user)
    is_global = not own_franchise_id
    if is_global:
        return franchise_id
    if franchise_id and franchise_id != own_franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for this franchise")
    return own_franchise_id


async def _generate_voucher_no(db: AsyncSession) -> str:
    count = (await db.execute(select(func.count()).select_from(CashVoucher))).scalar_one()
    return f"VCH-{str(count + 1).zfill(6)}"


async def _generate_manifest_no(db: AsyncSession) -> str:
    count = (await db.execute(select(func.count()).select_from(Manifest))).scalar_one()
    return f"MF-{str(count + 1).zfill(6)}"


async def create_expense(db: AsyncSession, data: ExpenseCreate, current_user: User) -> ExpenseOut:
    franchise_id = await _scope_franchise_id(db, current_user, data.franchise_id)
    expense = Expense(
        id=str(uuid.uuid4()),
        franchise_id=franchise_id,
        expense_date=data.expense_date,
        expense_head=data.expense_head,
        amount=data.amount,
        approved_by=data.approved_by,
        remarks=data.remarks,
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()
    await db.refresh(expense)
    return ExpenseOut.model_validate(expense)


async def list_expenses(db: AsyncSession, current_user: User, page: int, limit: int, date_from: date | None, date_to: date | None, franchise_id: str | None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(Expense.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(Expense.expense_date >= date_from)
    if date_to:
        filters.append(Expense.expense_date <= date_to)
    query = select(Expense).where(and_(*filters)).order_by(Expense.expense_date.desc())
    total = (await db.execute(select(func.count()).select_from(Expense).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(query.offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"items": [ExpenseOut.model_validate(row) for row in rows], "total": total, "page": page, "limit": limit, "pages": math.ceil(total / limit) if total else 0}


async def create_cash_voucher(db: AsyncSession, data: CashVoucherCreate, current_user: User) -> CashVoucherOut:
    franchise_id = await _scope_franchise_id(db, current_user, data.franchise_id)
    voucher = CashVoucher(
        id=str(uuid.uuid4()),
        voucher_no=await _generate_voucher_no(db),
        franchise_id=franchise_id,
        voucher_date=data.voucher_date,
        type=data.type,
        amount=data.amount,
        payment_mode=data.payment_mode,
        description=data.description,
        created_by=current_user.id,
    )
    db.add(voucher)
    await db.flush()
    await db.refresh(voucher)
    return CashVoucherOut.model_validate(voucher)


async def list_cash_vouchers(db: AsyncSession, current_user: User, page: int, limit: int, date_from: date | None, date_to: date | None, franchise_id: str | None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(CashVoucher.voucher_date >= date_from)
    if date_to:
        filters.append(CashVoucher.voucher_date <= date_to)
    total = (await db.execute(select(func.count()).select_from(CashVoucher).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.desc()).offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"items": [CashVoucherOut.model_validate(row) for row in rows], "total": total, "page": page, "limit": limit, "pages": math.ceil(total / limit) if total else 0}


async def create_attendance(db: AsyncSession, data: AttendanceCreate, current_user: User) -> AttendanceOut:
    user = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    franchise_id = await _scope_franchise_id(db, current_user, data.franchise_id or user.franchise_id)
    attendance = StaffAttendance(id=str(uuid.uuid4()), user_id=data.user_id, franchise_id=franchise_id, attendance_date=data.attendance_date, check_in=data.check_in, check_out=data.check_out, status=data.status, remarks=data.remarks)
    db.add(attendance)
    await db.flush()
    await db.refresh(attendance)
    return AttendanceOut.model_validate(attendance)


async def list_attendance(db: AsyncSession, current_user: User, page: int, limit: int, attendance_date: date | None, franchise_id: str | None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(StaffAttendance.franchise_id == scoped_franchise_id)
    if attendance_date:
        filters.append(StaffAttendance.attendance_date == attendance_date)
    total = (await db.execute(select(func.count()).select_from(StaffAttendance).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(select(StaffAttendance).where(and_(*filters)).order_by(StaffAttendance.attendance_date.desc()).offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"items": [AttendanceOut.model_validate(row) for row in rows], "total": total, "page": page, "limit": limit, "pages": math.ceil(total / limit) if total else 0}


async def create_manifest(db: AsyncSession, data: ManifestCreate, current_user: User) -> ManifestOut:
    franchise_id = await _scope_franchise_id(db, current_user, data.franchise_id)
    orders = (await db.execute(select(Order).where(Order.id.in_(data.order_ids)))).scalars().all()
    found_ids = {order.id for order in orders}
    missing = [order_id for order_id in data.order_ids if order_id not in found_ids]
    if missing:
        raise HTTPException(status_code=400, detail=f"Orders not found: {missing}")
    for order in orders:
        if franchise_id and order.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail=f"Order {order.order_number} is outside this franchise")
    manifest = Manifest(id=str(uuid.uuid4()), manifest_no=await _generate_manifest_no(db), franchise_id=franchise_id, manifest_date=data.manifest_date, vehicle_no=data.vehicle_no, route=data.route, created_by=current_user.id)
    db.add(manifest)
    await db.flush()
    for order in orders:
        db.add(ManifestOrder(id=str(uuid.uuid4()), manifest_id=manifest.id, order_id=order.id))
        order.status = OrderStatus.MANIFESTED
    await db.flush()
    await db.refresh(manifest)
    return ManifestOut.model_validate(manifest)


async def list_manifests(db: AsyncSession, current_user: User, page: int, limit: int, manifest_date: date | None, franchise_id: str | None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(Manifest.franchise_id == scoped_franchise_id)
    if manifest_date:
        filters.append(Manifest.manifest_date == manifest_date)
    total = (await db.execute(select(func.count()).select_from(Manifest).where(and_(*filters)))).scalar_one()
    rows = (await db.execute(select(Manifest).where(and_(*filters)).order_by(Manifest.manifest_date.desc()).offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"items": [ManifestOut.model_validate(row) for row in rows], "total": total, "page": page, "limit": limit, "pages": math.ceil(total / limit) if total else 0}


async def create_pod(db: AsyncSession, data: PodCreate, current_user: User) -> PodOut:
    order = (await db.execute(select(Order).where(Order.id == data.order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await _scope_franchise_id(db, current_user, order.franchise_id)
    existing = (await db.execute(select(PodRecord).where(PodRecord.order_id == data.order_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="POD already exists for this order")
    pod = PodRecord(id=str(uuid.uuid4()), order_id=data.order_id, receiver_name=data.receiver_name, received_at=data.received_at, delivery_staff_id=data.delivery_staff_id, otp_verified=data.otp_verified, signature_url=data.signature_url, remarks=data.remarks)
    db.add(pod)
    order.status = OrderStatus.DELIVERED
    await db.flush()
    await db.refresh(pod)
    return PodOut.model_validate(pod)


async def get_pod_by_order(db: AsyncSession, order_id: str, current_user: User) -> PodOut:
    pod = (await db.execute(select(PodRecord).where(PodRecord.order_id == order_id))).scalar_one_or_none()
    if not pod:
        raise HTTPException(status_code=404, detail="POD not found")
    await _scope_franchise_id(db, current_user, pod.order.franchise_id)
    return PodOut.model_validate(pod)
