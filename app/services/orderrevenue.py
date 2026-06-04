from datetime import date, datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import select, func, and_, between
from sqlalchemy.orm import selectinload
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.order import Order
from app.schemas.orderrevenue import DailyRevenueResponse




async def get_order_revenue_data(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    current_user: User,
    status_filter: Optional[str] = None,
    payment_method_filter: Optional[str] = None
):
    end_date_inclusive = end_date + timedelta(days=1)
    filters = [
        Order.created_at >= start_date,
        Order.created_at < end_date_inclusive,
        Order.status != "Cancelled",  # Exclude cancelled orders
        Order.order_value > 0
    ]
    if status_filter:
        filters.append(Order.status == status_filter)
    if payment_method_filter:
        filters.append(Order.payment_method == payment_method_filter)
    role_result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == current_user.id)
    )
    role_name = role_result.scalar_one_or_none()
    
    # Add user filter for non-admin users
    from app.dependencies.role_checker import is_global_user
    is_global = await is_global_user(db, current_user)
    if not is_global:
        filters.append(Order.created_by == current_user.id)
    
    # Get total revenue
    total_revenue_result = await db.execute(
        select(func.sum(Order.order_value))
        .where(*filters)
    )
    total_revenue = total_revenue_result.scalar() or 0
    
    # Get total orders count
    total_orders_result = await db.execute(
        select(func.count(Order.id))
        .where(*filters)
    )
    total_orders = total_orders_result.scalar() or 0
    
    # Get revenue by payment method
    revenue_by_payment = {}
    payment_methods = ["COD", "Prepaid", "To Pay"]
    
    for pm in payment_methods:
        pm_filters = filters + [Order.payment_method == pm]
        pm_result = await db.execute(
            select(func.sum(Order.order_value))
            .where(*pm_filters)
        )
        revenue_by_payment[pm] = float(pm_result.scalar() or 0)
    revenue_by_status = {}
    status_result = await db.execute(select(Order.status, func.sum(Order.order_value)).where(*filters).group_by(Order.status))
    for status, revenue in status_result.all():
        revenue_by_status[status] = float(revenue)
    daily_breakdown = []
    current_date = start_date
    while current_date <= end_date:
        day_start = current_date
        day_end = current_date + timedelta(days=1)
        day_filters = filters + [Order.created_at >= day_start,Order.created_at < day_end] 
        daily_orders_result = await db.execute(select(func.count(Order.id)).where(*day_filters))
        daily_orders = daily_orders_result.scalar() or 0
        daily_revenue_result = await db.execute(select(func.sum(Order.order_value)).where(*day_filters))
        daily_revenue = daily_revenue_result.scalar() or 0
        cod_filters = day_filters + [Order.payment_method == "COD"]
        cod_result = await db.execute(select(func.sum(Order.cod_amount)).where(*cod_filters))
        daily_cod = cod_result.scalar() or 0
        prepaid_filters = day_filters + [Order.payment_method == "Prepaid"]
        prepaid_result = await db.execute(select(func.sum(Order.order_value)).where(*prepaid_filters))
        daily_prepaid = prepaid_result.scalar() or 0
        topay_filters = day_filters + [Order.payment_method == "To Pay"]
        topay_result = await db.execute(select(func.sum(Order.order_value)).where(*topay_filters))
        daily_topay = topay_result.scalar() or 0
        orders_by_status = {}
        status_day_result = await db.execute(
            select(Order.status, func.count(Order.id), func.sum(Order.order_value))
            .where(*day_filters)
            .group_by(Order.status)
        )
        for status, count, revenue in status_day_result.all():
            orders_by_status[status] = {
                "count": count,
                "revenue": float(revenue) if revenue else 0
            }
        daily_breakdown.append(DailyRevenueResponse(
            date=current_date.isoformat(),
            total_orders=daily_orders,
            total_revenue=float(daily_revenue),
            total_cod_amount=float(daily_cod),
            total_prepaid_amount=float(daily_prepaid),
            total_to_pay_amount=float(daily_topay),
            orders_by_status=orders_by_status
        ))
        current_date += timedelta(days=1)
    return {
        "role_name": role_name,
        "total_revenue": float(total_revenue),
        "total_orders": total_orders,
        "average_order_value": float(total_revenue / total_orders) if total_orders > 0 else 0,
        "revenue_by_payment_method": revenue_by_payment,
        "revenue_by_status": revenue_by_status,
        "daily_breakdown": daily_breakdown
    }
