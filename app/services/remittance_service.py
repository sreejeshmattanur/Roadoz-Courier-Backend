import math
import uuid
import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.franchise import Franchise
from app.models.order import Order
from app.models.remittance import Remittance, RemittanceOrder
from app.models.role import Role
from app.models.user_role import UserRole
from app.schemas.remittance import (
    RemittanceSummaryOut,
    RemittanceOut,
    RemittanceListResponse,
    RemittanceCreateRequest,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    r = row.scalar_one_or_none()
    return r.lower() if r else None


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    result = await db.execute(select(Franchise).where(Franchise.user_id == user.id))
    franchise = result.scalar_one_or_none()
    return franchise.id if franchise else None


# ── Remittance Summary ───────────────────────────────────────────────────


async def get_remittance_summary(
    db: AsyncSession, current_user: User, franchise_id: str | None = None
) -> RemittanceSummaryOut:
    caller_role = await _get_caller_role_name(db, current_user.id)

    is_global = not await _resolve_franchise_id(db, current_user)
    if is_global and franchise_id:
        fid = franchise_id
    else:
        fid = await _resolve_franchise_id(db, current_user)
        if not fid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No franchise linked to this user",
            )

    # Total remitted
    remitted_result = await db.execute(
        select(
            func.coalesce(func.sum(Remittance.total_amount), 0),
            func.coalesce(func.sum(Remittance.orders_count), 0),
        )
        .where(
            and_(
                Remittance.franchise_id == fid,
                Remittance.status == "remitted",
            )
        )
    )
    remitted_row = remitted_result.one()
    remitted_amount = float(remitted_row[0])
    remitted_orders = int(remitted_row[1])

    # Due: delivered COD orders NOT yet linked to any remittance
    due_result = await db.execute(
        select(
            func.coalesce(func.sum(Order.cod_amount), 0),
            func.count(Order.id),
        )
        .where(
            and_(
                Order.franchise_id == fid,
                Order.payment_method == "COD",
                Order.status == "delivered",
                ~Order.id.in_(select(RemittanceOrder.order_id)),
            )
        )
    )
    due_row = due_result.one()
    due_amount = float(due_row[0])
    due_orders = int(due_row[1])

    return RemittanceSummaryOut(
        remitted_till_date=remitted_amount,
        remitted_orders=remitted_orders,
        due_amount=due_amount,
        due_orders=due_orders,
    )


# ── List remittances ─────────────────────────────────────────────────────


async def list_remittances(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    limit: int = 25,
    franchise_id: str | None = None,
    status_filter: str | None = None,
) -> RemittanceListResponse:
    caller_role = await _get_caller_role_name(db, current_user.id)

    filters = []

    is_global = not await _resolve_franchise_id(db, current_user)
    if is_global:
        if franchise_id:
            filters.append(Remittance.franchise_id == franchise_id)
    else:
        fid = await _resolve_franchise_id(db, current_user)
        if not fid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No franchise linked to this user",
            )
        filters.append(Remittance.franchise_id == fid)

    if status_filter:
        filters.append(Remittance.status == status_filter)

    query = select(Remittance).order_by(Remittance.created_at.desc())
    count_query = select(func.count()).select_from(Remittance)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    remittances = result.scalars().all()

    return RemittanceListResponse(
        items=[RemittanceOut.model_validate(r) for r in remittances],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


# ── Create remittance batch (admin) ──────────────────────────────────────


async def create_remittance(
    db: AsyncSession, data: RemittanceCreateRequest
) -> RemittanceOut:
    # Validate franchise
    result = await db.execute(select(Franchise).where(Franchise.id == data.franchise_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    # Validate all order IDs: must be delivered COD orders for this franchise, not already remitted
    orders = []
    for oid in data.order_ids:
        order_result = await db.execute(select(Order).where(Order.id == oid))
        order = order_result.scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {oid} not found",
            )
        if order.franchise_id != data.franchise_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {oid} does not belong to franchise {data.franchise_id}",
            )
        if order.payment_method != "COD":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {oid} is not a COD order",
            )
        if order.status != "delivered":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {oid} is not delivered (current status: {order.status})",
            )

        # Check not already in a remittance
        existing = await db.execute(
            select(RemittanceOrder).where(RemittanceOrder.order_id == oid)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {oid} is already included in a remittance",
            )

        orders.append(order)

    total_amount = sum(float(o.cod_amount) for o in orders)

    remittance = Remittance(
        id=str(uuid.uuid4()),
        franchise_id=data.franchise_id,
        total_amount=total_amount,
        orders_count=len(orders),
        status="pending",
        remarks=data.remarks,
    )
    db.add(remittance)
    await db.flush()

    for order in orders:
        ro = RemittanceOrder(
            id=str(uuid.uuid4()),
            remittance_id=remittance.id,
            order_id=order.id,
            cod_amount=float(order.cod_amount),
        )
        db.add(ro)

    await db.flush()
    await db.refresh(remittance)

    logger.info(
        f"Remittance created: id={remittance.id}, franchise={data.franchise_id}, "
        f"amount={total_amount}, orders={len(orders)}"
    )
    return RemittanceOut.model_validate(remittance)


# ── Mark remittance as remitted (admin) ──────────────────────────────────


async def mark_remitted(
    db: AsyncSession,
    remittance_id: str,
    reference_number: str | None = None,
    remarks: str | None = None,
) -> RemittanceOut:
    result = await db.execute(select(Remittance).where(Remittance.id == remittance_id))
    remittance = result.scalar_one_or_none()
    if not remittance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remittance not found")

    if remittance.status == "remitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remittance is already marked as remitted",
        )

    remittance.status = "remitted"
    remittance.remitted_at = datetime.utcnow()
    if reference_number:
        remittance.reference_number = reference_number
    if remarks:
        remittance.remarks = remarks

    await db.flush()
    await db.refresh(remittance)

    logger.info(f"Remittance marked remitted: id={remittance_id}, ref={reference_number}")
    return RemittanceOut.model_validate(remittance)


# ── Get single remittance ────────────────────────────────────────────────


async def get_remittance(
    db: AsyncSession, remittance_id: str, current_user: User
) -> RemittanceOut:
    result = await db.execute(select(Remittance).where(Remittance.id == remittance_id))
    remittance = result.scalar_one_or_none()
    if not remittance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remittance not found")

    # Access control
    is_global = not await _resolve_franchise_id(db, current_user)
    if not is_global:
        fid = await _resolve_franchise_id(db, current_user)
        if remittance.franchise_id != fid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return RemittanceOut.model_validate(remittance)
