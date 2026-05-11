from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.wallet import WalletTransaction, Wallet
from app.models.franchise import Franchise
from app.models.consignee import Consignee
from app.schemas.analytics import DashboardAnalyticsResponse

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")) # Using orders:view as generic dashboard access
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    
    # 1. Base conditions
    order_conditions = [Order.franchise_id == franchise_id] if franchise_id else []
    
    # Wallet base query
    wallet_txn_query = select(func.count(WalletTransaction.id))
    if franchise_id:
        wallet_id_subq = select(Wallet.id).where(Wallet.franchise_id == franchise_id).scalar_subquery()
        wallet_txn_query = wallet_txn_query.where(WalletTransaction.wallet_id == wallet_id_subq)

    # 2. Total Orders
    total_orders_query = select(func.count(Order.id)).where(*order_conditions)
    total_orders = (await db.execute(total_orders_query)).scalar_one() or 0

    # 3. RTO Orders
    rto_query = select(func.count(Order.id)).where(
        Order.status.in_([OrderStatus.RTO_IN_TRANSIT, OrderStatus.RTO_DELIVERED]),
        *order_conditions
    )
    rto_orders = (await db.execute(rto_query)).scalar_one() or 0

    # 4. Total Revenue (Super Admin) or Total Spend (Franchise)
    revenue_query = select(func.sum(Order.shipping_charge)).where(*order_conditions)
    total_revenue_or_spend = float((await db.execute(revenue_query)).scalar_one_or_none() or 0.0)

    # 5. Wallet Transactions Count
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
    delivered_query = select(func.count(Order.id)).where(Order.status == OrderStatus.DELIVERED, *order_conditions)
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

    # 10. Extra Counts (Admin only counts)
    extra_counts = {}
    if not franchise_id:
        total_users = (await db.execute(select(func.count(User.id)))).scalar_one() or 0
        total_franchises = (await db.execute(select(func.count(Franchise.id)))).scalar_one() or 0
        total_wallet_balance = (await db.execute(select(func.sum(Wallet.balance)))).scalar_one_or_none() or 0.0
        
        extra_counts["total_users"] = float(total_users)
        extra_counts["total_franchises"] = float(total_franchises)
        extra_counts["total_wallet_balance"] = float(total_wallet_balance)

    return DashboardAnalyticsResponse(
        total_orders=total_orders,
        rto_orders=rto_orders,
        total_revenue_or_spend=total_revenue_or_spend,
        wallet_transactions_count=wallet_transactions_count,
        cod_vs_prepaid=cod_vs_prepaid,
        order_statuses=order_statuses,
        delivered_vs_rto=delivered_vs_rto,
        statewise_orders=statewise_orders,
        extra_counts=extra_counts if extra_counts else None
    )
