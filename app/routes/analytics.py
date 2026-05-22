from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.wallet import WalletTransaction, Wallet
from app.models.franchise import Franchise
from app.models.consignee import Consignee
from app.models.operations import Expense, CashVoucher, StaffAttendance
from app.models.remittance import Remittance
from app.schemas.analytics import DashboardAnalyticsResponse
from math import ceil
router = APIRouter(prefix="/analytics", tags=["Analytics"])

async def _get_franchise_for_user(db: AsyncSession, user_id: str) -> str | None:
    result = await db.execute(select(Franchise).where(Franchise.user_id == user_id))
    franchise = result.scalar_one_or_none()
    return franchise.id if franchise else None

async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    return await _get_franchise_for_user(db, user.id)

@router.get("/dashboard", response_model=DashboardAnalyticsResponse)
async def get_dashboard_analytics(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    pagef: int = Query(1, ge=1),
    limitf: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")) # Using orders:view as generic dashboard access
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    
    # Convert dates to datetime bounds for datetime fields
    start_dt = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end_dt = datetime.combine(date_to, datetime.max.time()) if date_to else None
    
    # 1. Base conditions for Orders and Wallet Transactions
    order_conditions = []
    if franchise_id:
        order_conditions.append(Order.franchise_id == franchise_id)
    if start_dt:
        order_conditions.append(Order.created_at >= start_dt)
    if end_dt:
        order_conditions.append(Order.created_at <= end_dt)
        
    wallet_conditions = []
    if franchise_id:
        wallet_id_subq = select(Wallet.id).where(Wallet.franchise_id == franchise_id).scalar_subquery()
        wallet_conditions.append(WalletTransaction.wallet_id == wallet_id_subq)
    if start_dt:
        wallet_conditions.append(WalletTransaction.created_at >= start_dt)
    if end_dt:
        wallet_conditions.append(WalletTransaction.created_at <= end_dt)

    # 2. Total Orders
    total_orders_query = select(func.count(Order.id)).where(*order_conditions)
    total_orders = (await db.execute(total_orders_query)).scalar_one() or 0

    # 3. RTO Orders
    rto_query = select(func.count(Order.id)).where(
        and_(
            Order.status.in_([OrderStatus.RTO_IN_TRANSIT, OrderStatus.RTO_DELIVERED]),
            *order_conditions
        )
    )
    rto_orders = (await db.execute(rto_query)).scalar_one() or 0

    # 4. Total Revenue (Super Admin) or Total Spend (Franchise)
    revenue_query = select(func.sum(Order.shipping_charge)).where(*order_conditions)
    total_revenue_or_spend = float((await db.execute(revenue_query)).scalar_one_or_none() or 0.0)

    # 5. Wallet Transactions Count
    wallet_txn_query = select(func.count(WalletTransaction.id)).where(*wallet_conditions)
    wallet_transactions_count = (await db.execute(wallet_txn_query)).scalar_one() or 0

    # 6. COD vs Prepaid
    cod_vs_prepaid = {}
    cp_query = select(Order.payment_method, func.count(Order.id)).where(*order_conditions).group_by(Order.payment_method)
    for row in (await db.execute(cp_query)).all():
        cod_vs_prepaid[str(row[0])] = row[1]

    # 7. Order Statuses
    order_statuses = {}
    status_query = select(Order.status, func.count(Order.id)).where(*order_conditions).group_by(Order.status)
    for row in (await db.execute(status_query)).all():
        status_key = row[0].value if isinstance(row[0], OrderStatus) else str(row[0])
        order_statuses[status_key] = row[1]

    # 8. Delivered vs RTO
    delivered_query = select(func.count(Order.id)).where(
        and_(Order.status == OrderStatus.DELIVERED, *order_conditions)
    )
    delivered_count = (await db.execute(delivered_query)).scalar_one() or 0
    delivered_vs_rto = {
        "Delivered": delivered_count,
        "RTO": rto_orders
    }

    # 9. Statewise Orders
    statewise_orders = {}
    state_q = select(Consignee.state, func.count(Order.id)).join(Consignee, Order.consignee_id == Consignee.id).where(*order_conditions).group_by(Consignee.state)
    for row in (await db.execute(state_q)).all():
        statewise_orders[str(row[0])] = row[1]

    # 10. Operations and Financial Analytics conditions
    expense_conditions = []
    if franchise_id:
        expense_conditions.append(Expense.franchise_id == franchise_id)
    if date_from:
        expense_conditions.append(Expense.expense_date >= date_from)
    if date_to:
        expense_conditions.append(Expense.expense_date <= date_to)

    voucher_conditions = []
    if franchise_id:
        voucher_conditions.append(CashVoucher.franchise_id == franchise_id)
    if date_from:
        voucher_conditions.append(CashVoucher.voucher_date >= date_from)
    if date_to:
        voucher_conditions.append(CashVoucher.voucher_date <= date_to)

    attendance_conditions = []
    if franchise_id:
        attendance_conditions.append(StaffAttendance.franchise_id == franchise_id)
    if date_from:
        attendance_conditions.append(StaffAttendance.attendance_date >= date_from)
    if date_to:
        attendance_conditions.append(StaffAttendance.attendance_date <= date_to)

    remittance_conditions = []
    if franchise_id:
        remittance_conditions.append(Remittance.franchise_id == franchise_id)
    if start_dt:
        remittance_conditions.append(Remittance.created_at >= start_dt)
    if end_dt:
        remittance_conditions.append(Remittance.created_at <= end_dt)

    # Sum Expenses
    expense_q = select(func.coalesce(func.sum(Expense.amount), 0.0)).where(*expense_conditions)
    total_expenses = float((await db.execute(expense_q)).scalar_one() or 0.0)

    # Cash Vouchers Count
    vouchers_q = select(func.count(CashVoucher.id)).where(*voucher_conditions)
    total_vouchers = (await db.execute(vouchers_q)).scalar_one() or 0

    # Voucher Debits (payments outflow)
    debit_q = select(func.coalesce(func.sum(CashVoucher.amount), 0.0)).where(
        and_(CashVoucher.type == "payment", *voucher_conditions)
    )
    voucher_debit_sum = float((await db.execute(debit_q)).scalar_one() or 0.0)

    # Voucher Credits (receipts inflow)
    credit_q = select(func.coalesce(func.sum(CashVoucher.amount), 0.0)).where(
        and_(CashVoucher.type == "receipt", *voucher_conditions)
    )
    voucher_credit_sum = float((await db.execute(credit_q)).scalar_one() or 0.0)

    # Attendance Present Count
    attendance_q = select(func.count(StaffAttendance.id)).where(
        and_(StaffAttendance.status == "present", *attendance_conditions)
    )
    staff_attendance_present_count = (await db.execute(attendance_q)).scalar_one() or 0

    # Remittances pending
    remit_pending_q = select(func.coalesce(func.sum(Remittance.total_amount), 0.0)).where(
        and_(Remittance.status == "pending", *remittance_conditions)
    )
    remittance_pending_sum = float((await db.execute(remit_pending_q)).scalar_one() or 0.0)

    # Remittances complete
    remit_remitted_q = select(func.coalesce(func.sum(Remittance.total_amount), 0.0)).where(
        and_(Remittance.status == "remitted", *remittance_conditions)
    )
    remittance_remitted_sum = float((await db.execute(remit_remitted_q)).scalar_one() or 0.0)

    # 11. Extra Counts (Admin only counts)
    extra_counts = {}
    if not franchise_id:
        total_users = (await db.execute(select(func.count(User.id)))).scalar_one() or 0
        total_franchises = (await db.execute(select(func.count(Franchise.id)))).scalar_one() or 0
        total_wallet_balance = (await db.execute(select(func.sum(Wallet.balance)))).scalar_one_or_none() or 0.0
        
        extra_counts["total_users"] = float(total_users)
        extra_counts["total_franchises"] = float(total_franchises)
        extra_counts["total_wallet_balance"] = float(total_wallet_balance)
        
        
    # franchise order count    
    offset = (pagef - 1) * limitf   
    total_query = select(func.count(Franchise.id))
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    # main query with pagination
    franchise_orders_query = (
        select(
            Franchise.id,
            Franchise.name,
            Franchise.franchise_code,
            Franchise.email,
            Franchise.phone,
            func.count(Order.id).label("order_count")
        )
        .outerjoin(Order, Order.franchise_id == Franchise.id)
        .group_by(
            Franchise.id,
            Franchise.name,
            Franchise.franchise_code,
            Franchise.email,
            Franchise.phone
        )
        .order_by(func.count(Order.id).desc())
        .offset(offset)
        .limit(limitf)
    )

    franchise_orders_result = await db.execute(franchise_orders_query)

    franchise_orders_data = []

    for row in franchise_orders_result.all():
        franchise_orders_data.append({
            "franchise_name": row.name,
            "order_count": row.order_count,
        })

    response = {
        "pagination": {
            "page": pagef,
            "limit": limitf,
            "total": total,
            "total_pages": ceil(total / limitf) if total else 1,
            "has_next": pagef * limitf < total,
            "has_prev": pagef > 1
        },
        "franchise_orders_data": franchise_orders_data
    }       
    return DashboardAnalyticsResponse(
        total_orders=total_orders,
        rto_orders=rto_orders,
        total_revenue_or_spend=total_revenue_or_spend,
        wallet_transactions_count=wallet_transactions_count,
        cod_vs_prepaid=cod_vs_prepaid,
        order_statuses=order_statuses,
        delivered_vs_rto=delivered_vs_rto,
        statewise_orders=statewise_orders,
        total_expenses=total_expenses,
        total_vouchers=total_vouchers,
        voucher_debit_sum=voucher_debit_sum,
        voucher_credit_sum=voucher_credit_sum,
        staff_attendance_present_count=staff_attendance_present_count,
        remittance_pending_sum=remittance_pending_sum,
        remittance_remitted_sum=remittance_remitted_sum,
        franchise_orders_data=response  if response else None ,
        extra_counts=extra_counts if extra_counts else None
        
    )
