import calendar
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select, Date, DateTime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consignee import Consignee
from app.models.franchise import Franchise
from app.models.invoice import Invoice, InvoiceOrder
from app.models.order import Order, OrderStatus
from app.models.remittance import RemittanceOrder
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.models.operations import Expense, CashVoucher, StaffAttendance, Manifest, PodRecord
from app.models.activity_log import ActivityLog



def _to_float(value: Any) -> float:
    return round(float(value or 0), 2)


def _status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _date_range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to, datetime.max.time()) if date_to else None
    return start, end


async def _resolve_dates_and_opening(
    db: AsyncSession,
    model: Any,
    date_column: Any,
    date_from: date | None,
    date_to: date | None,
    amount_columns: Any = None,
    additional_filters: list[Any] = None
) -> tuple[date, date, Any]:
    """
    Calculates the accumulated opening amount from date_from to date_to - 1.
    Returns (date_to, date_to, opening_amount) so that the report only fetches items for date_to.
    """
    if additional_filters is None:
        additional_filters = []
        
    resolved_to = date_to or date.today()
    
    if date_from:
        real_from = date_from
    else:
        query = select(func.min(date_column))
        if additional_filters:
            query = query.where(and_(*additional_filters))
        earliest_time = (await db.execute(query)).scalar()
        if earliest_time:
            if isinstance(earliest_time, datetime):
                real_from = earliest_time.date()
            elif isinstance(earliest_time, date):
                real_from = earliest_time
            else:
                real_from = date(2026, 1, 1)
        else:
            real_from = date(2026, 1, 1)
            
    if amount_columns is None:
        return resolved_to, resolved_to, 0.0
        
    is_list = isinstance(amount_columns, list)
    cols = amount_columns if is_list else [amount_columns]
    
    start_datetime = datetime.combine(real_from, datetime.min.time())
    end_datetime = datetime.combine(resolved_to, datetime.min.time())
    
    if isinstance(date_column.type, DateTime):
        boundary_start = start_datetime
        boundary_end = end_datetime
    else:
        boundary_start = real_from
        boundary_end = resolved_to
        
    select_exprs = [func.coalesce(func.sum(col), 0) for col in cols]
    query = select(*select_exprs).where(and_(
        date_column >= boundary_start,
        date_column < boundary_end
    ))
    
    if additional_filters:
        query = query.where(and_(*additional_filters))
        
    res = (await db.execute(query)).all()
    if res:
        opening_values = [round(float(val), 2) for val in res[0]]
    else:
        opening_values = [0.0] * len(cols)
        
    if is_list:
        return resolved_to, resolved_to, opening_values
    else:
        return resolved_to, resolved_to, opening_values[0]


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    role = row.scalar_one_or_none()
    return role.lower() if role else None


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    result = await db.execute(select(Franchise).where(Franchise.user_id == user.id))
    franchise = result.scalar_one_or_none()
    return franchise.id if franchise else None


async def _scope_franchise_id(db: AsyncSession, current_user: User, franchise_id: str | None = None) -> str | None:
    caller_role = await _get_caller_role_name(db, current_user.id)
    if caller_role == "super_admin":
        return franchise_id
    resolved = await _resolve_franchise_id(db, current_user)
    if franchise_id and resolved and franchise_id != resolved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for this franchise")
    return resolved


def _order_filters(scoped_franchise_id: str | None, date_from: date | None, date_to: date | None) -> list[Any]:
    start, end = _date_range(date_from, date_to)
    filters = []
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    if start:
        filters.append(Order.created_at >= start)
    if end:
        filters.append(Order.created_at <= end)
    return filters


async def daily_booking_report(
    db: AsyncSession,
    current_user: User,
    report_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    if date_from or date_to:
        start_date = date_from
        end_date = date_to
    else:
        start_date = report_date or date.today()
        end_date = report_date or date.today()

    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_amount = await _resolve_dates_and_opening(
        db, Order, Order.created_at, start_date, end_date, Order.shipping_charge, additional_filters
    )

    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    result = await db.execute(
        select(Order)
        .where(and_(*filters))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    items = [
        {
            "booking_no": order.order_number,
            "sender": order.pickup_address.contact_name if order.pickup_address else None,
            "receiver": order.consignee.name if order.consignee else None,
            "destination": order.consignee.city if order.consignee else None,
            "weight": _to_float(order.applicable_weight_kg),
            "amount": _to_float(order.shipping_charge),
            "status": _status_value(order.status),
        }
        for order in orders
    ]
    total_amount = _to_float(sum(item["amount"] for item in items))

    return {
        "report": "Daily Booking Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_amount,
        "total_bookings": len(orders),
        "total_amount": total_amount,
        "items": items,
        "totals": {
            "amount": _to_float(float(opening_amount) + float(total_amount))
        }
    }


async def customer_wise_booking_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_vals = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, [Order.shipping_charge, Order.cod_amount], additional_filters
    )

    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    rows = (
        await db.execute(
            select(
                Consignee.name,
                func.count(Order.id),
                func.coalesce(func.sum(Order.shipping_charge), 0),
                func.coalesce(func.sum(Order.cod_amount), 0),
            )
            .join(Consignee, Order.consignee_id == Consignee.id)
            .where(and_(*filters))
            .group_by(Consignee.name)
            .order_by(func.coalesce(func.sum(Order.shipping_charge), 0).desc())
        )
    ).all()

    items = [
        {
            "customer": row[0],
            "bookings": row[1],
            "revenue": _to_float(row[2]),
            "pending_amount": _to_float(row[3]),
        }
        for row in rows
    ]
    total_rev = _to_float(sum(item["revenue"] for item in items))
    total_pending = _to_float(sum(item["pending_amount"] for item in items))

    return {
        "report": "Customer Wise Booking Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_revenue": opening_vals[0],
        "opening_pending_amount": opening_vals[1],
        "items": items,
        "totals": {
            "revenue": _to_float(float(opening_vals[0]) + float(total_rev)),
            "pending_amount": _to_float(float(opening_vals[1]) + float(total_pending))
        }
    }


async def service_type_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_revenue = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.shipping_charge, additional_filters
    )

    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    rows = (
        await db.execute(
            select(Order.order_type, func.count(Order.id), func.coalesce(func.sum(Order.shipping_charge), 0))
            .where(and_(*filters))
            .group_by(Order.order_type)
        )
    ).all()

    items = [
        {"service_type": row[0], "total_bookings": row[1], "revenue": _to_float(row[2])}
        for row in rows
    ]
    total_rev = _to_float(sum(item["revenue"] for item in items))

    return {
        "report": "Service Type Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_revenue,
        "items": items,
        "totals": {
            "revenue": _to_float(float(opening_revenue) + float(total_rev))
        }
    }


async def delivery_status_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    result = await db.execute(select(Order).where(and_(*filters)).order_by(Order.updated_at.desc()))
    orders = result.scalars().all()
    return {
        "report": "Delivery Status Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": [
            {
                "awb_no": order.order_number,
                "receiver": order.consignee.name if order.consignee else None,
                "delivery_date": order.updated_at.date() if _status_value(order.status) == OrderStatus.DELIVERED.value else None,
                "status": _status_value(order.status),
                "pod": "Available" if _status_value(order.status) == OrderStatus.DELIVERED.value else "Pending",
            }
            for order in orders
        ],
    }


async def pending_delivery_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    terminal_statuses = [OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST]
    filters = [
        Order.status.notin_(terminal_statuses),
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time()),
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    result = await db.execute(select(Order).where(and_(*filters)).order_by(Order.created_at.asc()))
    orders = result.scalars().all()
    today = datetime.utcnow().date()
    return {
        "report": "Pending Delivery Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": [
            {
                "awb_no": order.order_number,
                "destination": order.consignee.city if order.consignee else None,
                "pending_days": max((today - order.created_at.date()).days, 0),
                "reason": _status_value(order.status),
            }
            for order in orders
        ],
    }


async def cod_pending_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [
        Order.payment_method == "COD",
        Order.cod_amount.is_not(None),
        ~Order.id.in_(select(RemittanceOrder.order_id)),
    ]
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_pending = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.cod_amount, additional_filters
    )

    filters = [
        Order.payment_method == "COD",
        Order.cod_amount.is_not(None),
        ~Order.id.in_(select(RemittanceOrder.order_id)),
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time()),
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)

    result = await db.execute(
        select(Order, Franchise.name)
        .outerjoin(Franchise, Order.franchise_id == Franchise.id)
        .where(and_(*filters))
        .order_by(Order.created_at.desc())
    )
    rows = result.all()
    items = [
        {
            "booking_no": order.order_number,
            "merchant": franchise_name or order.franchise_id,
            "pending_amount": _to_float(order.cod_amount),
            "status": _status_value(order.status),
        }
        for order, franchise_name in rows
    ]
    total_pending = _to_float(sum(item["pending_amount"] for item in items))

    return {
        "report": "COD Pending Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_pending,
        "total_pending_amount": total_pending,
        "items": items,
        "totals": {
            "pending_amount": _to_float(float(opening_pending) + float(total_pending))
        }
    }


async def gst_sales_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Invoice.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_vals = await _resolve_dates_and_opening(
        db, Invoice, Invoice.created_at, date_from, date_to, [Invoice.subtotal, Invoice.tax_amount, Invoice.total_amount], additional_filters
    )

    filters = []
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
    filters.append(Invoice.created_at >= datetime.combine(resolved_from, datetime.min.time()))
    filters.append(Invoice.created_at <= datetime.combine(resolved_to, datetime.max.time()))

    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.desc()))).scalars().all()
    items = [
        {
            "invoice_no": invoice.invoice_number,
            "taxable_amount": _to_float(invoice.subtotal),
            "cgst": _to_float(float(invoice.tax_amount or 0) / 2),
            "sgst": _to_float(float(invoice.tax_amount or 0) / 2),
            "igst": 0.0,
            "total": _to_float(invoice.total_amount),
        }
        for invoice in invoices
    ]

    total_taxable = _to_float(sum(item["taxable_amount"] for item in items))
    total_cgst = _to_float(sum(item["cgst"] for item in items))
    total_sgst = _to_float(sum(item["sgst"] for item in items))
    total_igst = 0.0
    total_total = _to_float(sum(item["total"] for item in items))

    return {
        "report": "GST Sales Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_taxable_amount": opening_vals[0],
        "opening_cgst": _to_float(opening_vals[1] / 2),
        "opening_sgst": _to_float(opening_vals[1] / 2),
        "opening_igst": 0.0,
        "opening_total": opening_vals[2],
        "items": items,
        "totals": {
            "taxable_amount": _to_float(float(opening_vals[0]) + float(total_taxable)),
            "cgst": _to_float(float(_to_float(opening_vals[1] / 2)) + float(total_cgst)),
            "sgst": _to_float(float(_to_float(opening_vals[1] / 2)) + float(total_sgst)),
            "igst": total_igst,
            "total": _to_float(float(opening_vals[2]) + float(total_total))
        }
    }


async def franchise_settlement_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_revenue = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.shipping_charge, additional_filters
    )

    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    rows = (
        await db.execute(
            select(
                Franchise.id,
                Franchise.name,
                func.coalesce(func.sum(Order.shipping_charge), 0),
                func.count(Order.id),
            )
            .join(Order, Order.franchise_id == Franchise.id)
            .where(and_(*filters))
            .group_by(Franchise.id, Franchise.name)
        )
    ).all()

    items = []
    for row in rows:
        revenue = _to_float(row[2])
        ho_share = _to_float(revenue * 0.7)
        franchise_share = _to_float(revenue * 0.3)
        items.append(
            {
                "franchise_id": row[0],
                "franchise": row[1],
                "shipments": row[3],
                "revenue": revenue,
                "ho_share": ho_share,
                "franchise_share": franchise_share,
                "net_payable": franchise_share,
            }
        )

    total_revenue = _to_float(sum(item["revenue"] for item in items))
    total_ho = _to_float(sum(item["ho_share"] for item in items))
    total_franchise = _to_float(sum(item["franchise_share"] for item in items))
    total_payable = _to_float(sum(item["net_payable"] for item in items))

    opening_rev_val = _to_float(opening_revenue)
    opening_ho = _to_float(opening_rev_val * 0.7)
    opening_franchise = _to_float(opening_rev_val * 0.3)

    return {
        "report": "Franchise Settlement Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_revenue": opening_rev_val,
        "opening_ho_share": opening_ho,
        "opening_franchise_share": opening_franchise,
        "opening_net_payable": opening_franchise,
        "items": items,
        "totals": {
            "revenue": _to_float(float(opening_rev_val) + float(total_revenue)),
            "ho_share": _to_float(float(opening_ho) + float(total_ho)),
            "franchise_share": _to_float(float(opening_franchise) + float(total_franchise)),
            "net_payable": _to_float(float(opening_franchise) + float(total_payable))
        }
    }


async def monthly_revenue_analysis(db: AsyncSession, current_user: User, year: int | None = None, franchise_id: str | None = None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_year = year or date.today().year

    # Opening balance prior to the target year
    start_of_year = datetime(target_year, 1, 1)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    opening_revenue = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(Order.created_at < start_of_year, *additional_filters))
    )).scalar_one()

    items = []
    previous_revenue = None
    for month in range(1, 13):
        start = datetime(target_year, month, 1)
        end = datetime(target_year, month, calendar.monthrange(target_year, month)[1], 23, 59, 59)
        filters = [Order.created_at >= start, Order.created_at <= end]
        if scoped_franchise_id:
            filters.append(Order.franchise_id == scoped_franchise_id)
        revenue = _to_float((await db.execute(select(func.coalesce(func.sum(Order.shipping_charge), 0)).where(and_(*filters)))).scalar_one())
        growth = 0.0 if not previous_revenue else round(((revenue - previous_revenue) / previous_revenue) * 100, 2)
        items.append({"month": calendar.month_abbr[month], "revenue": revenue, "expenses": 0.0, "profit": revenue, "growth_percent": growth})
        previous_revenue = revenue

    total_revenue = _to_float(sum(item["revenue"] for item in items))
    total_expenses = _to_float(sum(item["expenses"] for item in items))
    total_profit = _to_float(sum(item["profit"] for item in items))

    return {
        "report": "Monthly Revenue Analysis",
        "year": target_year,
        "opening_revenue": _to_float(opening_revenue),
        "opening_expenses": 0.0,
        "opening_profit": _to_float(opening_revenue),
        "items": items,
        "totals": {
            "revenue": _to_float(float(opening_revenue) + float(total_revenue)),
            "expenses": total_expenses,
            "profit": _to_float(float(opening_revenue) + float(total_profit))
        }
    }


async def top_customer_report(
    db: AsyncSession,
    current_user: User,
    limit: int = 10,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    data = await customer_wise_booking_report(db, current_user, date_from, date_to, franchise_id)
    data["report"] = "Top Customer Report"
    data["items"] = sorted(data["items"], key=lambda item: item["revenue"], reverse=True)[:limit]
    
    total_rev = _to_float(sum(item["revenue"] for item in data["items"]))
    total_pending = _to_float(sum(item["pending_amount"] for item in data["items"]))
    data["totals"] = {
        "revenue": _to_float(float(data.get("opening_revenue", 0.0)) + float(total_rev)),
        "pending_amount": _to_float(float(data.get("opening_pending_amount", 0.0)) + float(total_pending))
    }
    return data


async def delivery_efficiency_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    rows = (
        await db.execute(
            select(Franchise.id, Franchise.name, Order.status, func.count(Order.id))
            .join(Order, Order.franchise_id == Franchise.id)
            .where(and_(*filters))
            .group_by(Franchise.id, Franchise.name, Order.status)
        )
    ).all()
    grouped: dict[str, dict[str, Any]] = {}
    for franchise_id_value, franchise_name, order_status, count in rows:
        item = grouped.setdefault(
            franchise_id_value,
            {"franchise_id": franchise_id_value, "branch": franchise_name, "assigned": 0, "delivered": 0, "pending": 0},
        )
        item["assigned"] += count
        if _status_value(order_status) == OrderStatus.DELIVERED.value:
            item["delivered"] += count
        else:
            item["pending"] += count
    for item in grouped.values():
        item["efficiency_percent"] = round((item["delivered"] / item["assigned"]) * 100, 2) if item["assigned"] else 0.0
        
    items = list(grouped.values())
    total_assigned = sum(item["assigned"] for item in items)
    total_delivered = sum(item["delivered"] for item in items)
    total_pending = sum(item["pending"] for item in items)
    overall_efficiency = round((total_delivered / total_assigned) * 100, 2) if total_assigned else 0.0

    return {
        "report": "Delivery Efficiency Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": items,
        "totals": {
            "assigned": total_assigned,
            "delivered": total_delivered,
            "pending": total_pending,
            "efficiency_percent": overall_efficiency
        }
    }


async def day_close_report(
    db: AsyncSession,
    current_user: User,
    report_date: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_date = report_date or date.today()
    
    opening_vouchers = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < target_date,
            CashVoucher.type == "receipt",
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    opening_payments = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < target_date,
            CashVoucher.type == "payment",
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    opening_expenses = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(
            Expense.expense_date < target_date,
            Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    opening_balance = _to_float(float(opening_vouchers) - float(opening_payments) - float(opening_expenses))
    
    today_collection = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date == target_date,
            CashVoucher.type == "receipt",
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    today_payments = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date == target_date,
            CashVoucher.type == "payment",
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    today_expenses_table = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(
            Expense.expense_date == target_date,
            Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    
    total_collection = _to_float(today_collection)
    total_expenses = _to_float(float(today_payments) + float(today_expenses_table))
    closing_balance = _to_float(float(opening_balance) + float(total_collection) - float(total_expenses))
    
    items = [{
        "opening_balance": opening_balance,
        "collection": total_collection,
        "expenses": total_expenses,
        "closing_balance": closing_balance
    }]
    
    return {
        "report": "Day Close Report",
        "date": target_date,
        "opening_balance": opening_balance,
        "items": items,
        "totals": {
            "opening_balance": opening_balance,
            "collection": total_collection,
            "expenses": total_expenses,
            "closing_balance": closing_balance
        }
    }


async def branch_activity_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [CashVoucher.type == "receipt"]
    if scoped_franchise_id:
        additional_filters.append(CashVoucher.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_collections = await _resolve_dates_and_opening(
        db, CashVoucher, CashVoucher.voucher_date, date_from, date_to, CashVoucher.amount, additional_filters
    )

    franchise_filters = []
    if scoped_franchise_id:
        franchise_filters.append(Franchise.id == scoped_franchise_id)
    franchises = (await db.execute(select(Franchise).where(and_(*franchise_filters)))).scalars().all()
    items = []
    for f in franchises:
        bookings = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                *_order_filters(None, resolved_from, resolved_to)[1:]
            ))
        )).scalar_one()
        
        deliveries = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                Order.status == OrderStatus.DELIVERED,
                *_order_filters(None, resolved_from, resolved_to)[1:]
            ))
        )).scalar_one()
        
        terminal_statuses = [OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST]
        pending = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                Order.status.notin_(terminal_statuses),
                *_order_filters(None, resolved_from, resolved_to)[1:]
            ))
        )).scalar_one()
        
        collections = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                CashVoucher.voucher_date >= resolved_from,
                CashVoucher.voucher_date <= resolved_to
            ))
        )).scalar_one()
        
        items.append({
            "branch": f.name,
            "bookings": bookings,
            "deliveries": deliveries,
            "collections": _to_float(collections),
            "pending": pending
        })
        
    total_bookings = sum(item["bookings"] for item in items)
    total_deliveries = sum(item["deliveries"] for item in items)
    total_collections = _to_float(sum(item["collections"] for item in items))
    total_pending = sum(item["pending"] for item in items)

    return {
        "report": "Branch Activity Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_collections": opening_collections,
        "items": items,
        "totals": {
            "bookings": total_bookings,
            "deliveries": total_deliveries,
            "collections": _to_float(float(opening_collections) + float(total_collections)),
            "pending": total_pending
        }
    }


async def user_activity_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    filters = []
    if scoped_franchise_id:
        filters.append(User.franchise_id == scoped_franchise_id)
    users = (await db.execute(select(User).where(and_(*filters)))).scalars().all()
    items = []
    for u in users:
        login_row = (await db.execute(
            select(ActivityLog.created_at)
            .where(and_(
                ActivityLog.user_id == u.id,
                ActivityLog.path.contains("login")
            ))
            .order_by(ActivityLog.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        logout_row = (await db.execute(
            select(ActivityLog.created_at)
            .where(and_(
                ActivityLog.user_id == u.id,
                ActivityLog.path.contains("logout")
            ))
            .order_by(ActivityLog.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        tx_count = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.created_by == u.id,
                Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
                Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
            ))
        )).scalar_one()
        
        items.append({
            "user": u.name or u.email,
            "login_time": login_row.strftime("%Y-%m-%d %H:%M:%S") if login_row else "N/A",
            "logout_time": logout_row.strftime("%Y-%m-%d %H:%M:%S") if logout_row else "N/A",
            "transactions": tx_count
        })
    return {
        "report": "User Activity Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": items
    }


async def returned_shipment_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    filters = [
        Order.status.in_([OrderStatus.RETURNED, OrderStatus.RTO_DELIVERED, OrderStatus.RTO_IN_TRANSIT]),
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
        
    orders = (await db.execute(select(Order).where(and_(*filters)).order_by(Order.updated_at.desc()))).scalars().all()
    return {
        "report": "Returned Shipment Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": [
            {
                "awb_no": o.order_number,
                "return_reason": (o.consignee.name + " Refused") if o.consignee else "Returned to Sender",
                "status": _status_value(o.status)
            }
            for o in orders
        ]
    }


async def collection_summary_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [CashVoucher.type == "receipt"]
    if scoped_franchise_id:
        additional_filters.append(CashVoucher.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_amount = await _resolve_dates_and_opening(
        db, CashVoucher, CashVoucher.voucher_date, date_from, date_to, CashVoucher.amount, additional_filters
    )

    filters = [
        CashVoucher.type == "receipt",
        CashVoucher.voucher_date >= resolved_from,
        CashVoucher.voucher_date <= resolved_to
    ]
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
        
    vouchers = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.desc()))).scalars().all()
    items = [
        {
            "receipt_no": v.voucher_no,
            "customer": v.franchise.name if v.franchise else "Walk-in Customer",
            "amount": _to_float(v.amount),
            "payment_mode": v.payment_mode
        }
        for v in vouchers
    ]
    total_amount = _to_float(sum(item["amount"] for item in items))

    return {
        "report": "Collection Summary Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_amount,
        "items": items,
        "totals": {
            "amount": _to_float(float(opening_amount) + float(total_amount))
        }
    }


async def outstanding_collection_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [Invoice.status == "pending"]
    if scoped_franchise_id:
        additional_filters.append(Invoice.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_balance = await _resolve_dates_and_opening(
        db, Invoice, Invoice.created_at, date_from, date_to, Invoice.total_amount, additional_filters
    )

    filters = [
        Invoice.status == "pending",
        Invoice.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Invoice.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.asc()))).scalars().all()
    
    items = [
        {
            "customer": inv.franchise.name if inv.franchise else inv.franchise_id,
            "invoice": inv.invoice_number,
            "balance": _to_float(inv.total_amount),
            "due_date": (inv.created_at + timedelta(days=15)).date()
        }
        for inv in invoices
    ]
    total_balance = _to_float(sum(item["balance"] for item in items))

    return {
        "report": "Outstanding Collection Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_balance": opening_balance,
        "items": items,
        "totals": {
            "balance": _to_float(float(opening_balance) + float(total_balance))
        }
    }


async def daily_collection_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [CashVoucher.type == "receipt"]
    if scoped_franchise_id:
        additional_filters.append(CashVoucher.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_total = await _resolve_dates_and_opening(
        db, CashVoucher, CashVoucher.voucher_date, date_from, date_to, CashVoucher.amount, additional_filters
    )

    # Let's resolve cash vs bank opening split
    opening_cash = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < resolved_from,
            CashVoucher.type == "receipt",
            CashVoucher.payment_mode.ilike("%cash%"),
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()

    opening_upi = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < resolved_from,
            CashVoucher.type == "receipt",
            CashVoucher.payment_mode.ilike("%upi%"),
            CashVoucher.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()

    opening_bank = _to_float(float(opening_total) - float(opening_cash) - float(opening_upi))

    filters = [
        CashVoucher.type == "receipt",
        CashVoucher.voucher_date >= resolved_from,
        CashVoucher.voucher_date <= resolved_to
    ]
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
        
    vouchers = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.desc()))).scalars().all()
    grouped = {}
    for v in vouchers:
        dt_str = v.voucher_date.strftime("%Y-%m-%d")
        row = grouped.setdefault(dt_str, {"date": dt_str, "cash": 0.0, "upi": 0.0, "bank_transfer": 0.0, "total": 0.0})
        mode = v.payment_mode.lower()
        amt = float(v.amount)
        row["total"] += amt
        if "cash" in mode:
            row["cash"] += amt
        elif "upi" in mode:
            row["upi"] += amt
        else:
            row["bank_transfer"] += amt
            
    for row in grouped.values():
        row["cash"] = round(row["cash"], 2)
        row["upi"] = round(row["upi"], 2)
        row["bank_transfer"] = round(row["bank_transfer"], 2)
        row["total"] = round(row["total"], 2)
        
    items = sorted(grouped.values(), key=lambda r: r["date"], reverse=True)
    total_cash = _to_float(sum(item["cash"] for item in items))
    total_upi = _to_float(sum(item["upi"] for item in items))
    total_bank = _to_float(sum(item["bank_transfer"] for item in items))
    total_total = _to_float(sum(item["total"] for item in items))

    return {
        "report": "Daily Collection Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_cash": _to_float(opening_cash),
        "opening_upi": _to_float(opening_upi),
        "opening_bank_transfer": opening_bank,
        "opening_total": _to_float(opening_total),
        "items": items,
        "totals": {
            "cash": _to_float(float(opening_cash) + float(total_cash)),
            "upi": _to_float(float(opening_upi) + float(total_upi)),
            "bank_transfer": _to_float(float(opening_bank) + float(total_bank)),
            "total": _to_float(float(opening_total) + float(total_total))
        }
    }


async def cod_settlement_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
    ]
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_cod = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.cod_amount, additional_filters
    )

    filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
        
    rows = (await db.execute(
        select(
            Franchise.name,
            func.coalesce(func.sum(Order.cod_amount), 0),
        )
        .join(Franchise, Order.franchise_id == Franchise.id)
        .where(and_(*filters))
        .group_by(Franchise.name)
    )).all()
    
    items = []
    for row in rows:
        merchant = row[0]
        cod_amount = _to_float(row[1])
        commission = _to_float(cod_amount * 0.05)
        net_payable = _to_float(cod_amount - commission)
        items.append({
            "merchant": merchant,
            "cod_amount": cod_amount,
            "commission": commission,
            "net_payable": net_payable
        })

    total_cod = _to_float(sum(item["cod_amount"] for item in items))
    total_commission = _to_float(sum(item["commission"] for item in items))
    total_payable = _to_float(sum(item["net_payable"] for item in items))

    opening_cod_val = _to_float(opening_cod)
    opening_comm_val = _to_float(opening_cod_val * 0.05)
    opening_net_val = _to_float(opening_cod_val - opening_comm_val)

    return {
        "report": "COD Settlement Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_cod_val,
        "opening_commission": opening_comm_val,
        "opening_net_payable": opening_net_val,
        "items": items,
        "totals": {
            "cod_amount": _to_float(float(opening_cod_val) + float(total_cod)),
            "commission": _to_float(float(opening_comm_val) + float(total_commission)),
            "net_payable": _to_float(float(opening_net_val) + float(total_payable))
        }
    }


async def cod_commission_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
    ]
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_cod = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.cod_amount, additional_filters
    )

    filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
        
    rows = (await db.execute(
        select(
            Franchise.name,
            func.coalesce(func.sum(Order.cod_amount), 0),
        )
        .join(Franchise, Order.franchise_id == Franchise.id)
        .where(and_(*filters))
        .group_by(Franchise.name)
    )).all()
    
    items = [
        {
            "merchant": row[0],
            "commission_percent": 5.0,
            "amount": _to_float(float(row[1]) * 0.05)
        }
        for row in rows
    ]
    total_commission = _to_float(sum(item["amount"] for item in items))

    return {
        "report": "COD Commission Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": _to_float(opening_cod * 0.05),
        "items": items,
        "totals": {
            "amount": _to_float(float(opening_cod * 0.05) + float(total_commission))
        }
    }


async def cash_book_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(CashVoucher.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, CashVoucher, CashVoucher.voucher_date, date_from, date_to, None, additional_filters
    )

    # Let's resolve the opening balance before resolved_from
    opening_credit = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < resolved_from,
            CashVoucher.type == "receipt",
            *additional_filters
        ))
    )).scalar_one()

    opening_debit = (await db.execute(
        select(func.coalesce(func.sum(CashVoucher.amount), 0))
        .where(and_(
            CashVoucher.voucher_date < resolved_from,
            CashVoucher.type == "payment",
            *additional_filters
        ))
    )).scalar_one()

    opening_balance = _to_float(float(opening_credit) - float(opening_debit))

    filters = [
        CashVoucher.voucher_date >= resolved_from,
        CashVoucher.voucher_date <= resolved_to
    ]
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
        
    vouchers = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.asc()))).scalars().all()
    items = []
    balance = opening_balance
    total_debit = 0.0
    total_credit = 0.0
    
    for v in vouchers:
        credit = float(v.amount) if v.type == "receipt" else 0.0
        debit = float(v.amount) if v.type == "payment" else 0.0
        balance += credit - debit
        total_credit += credit
        total_debit += debit
        items.append({
            "date": v.voucher_date.strftime("%Y-%m-%d"),
            "voucher_no": v.voucher_no,
            "debit": _to_float(debit),
            "credit": _to_float(credit),
            "balance": _to_float(balance)
        })

    return {
        "report": "Cash Book Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_balance": opening_balance,
        "items": items,
        "totals": {
            "debit": _to_float(total_debit),
            "credit": _to_float(total_credit),
            "balance": _to_float(balance)
        }
    }


async def expense_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Expense.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_amount = await _resolve_dates_and_opening(
        db, Expense, Expense.expense_date, date_from, date_to, Expense.amount, additional_filters
    )

    filters = [
        Expense.expense_date >= resolved_from,
        Expense.expense_date <= resolved_to
    ]
    if scoped_franchise_id:
        filters.append(Expense.franchise_id == scoped_franchise_id)
        
    expenses = (await db.execute(select(Expense).where(and_(*filters)).order_by(Expense.expense_date.desc()))).scalars().all()
    items = [
        {
            "expense_head": exp.expense_head,
            "amount": _to_float(exp.amount),
            "approved_by": exp.approved_by or "Super Admin"
        }
        for exp in expenses
    ]
    total_amount = _to_float(sum(item["amount"] for item in items))

    return {
        "report": "Expense Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_amount": opening_amount,
        "items": items,
        "totals": {
            "amount": _to_float(float(opening_amount) + float(total_amount))
        }
    }


async def profit_loss_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    # We resolve date using Order.created_at as primary transaction date
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, additional_filters
    )

    # Let's compute opening values before resolved_from
    opening_revenue_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(
            Order.created_at < datetime.combine(resolved_from, datetime.min.time()),
            *additional_filters
        ))
    )).scalar_one()

    opening_cod_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.cod_amount), 0))
        .where(and_(
            Order.payment_method == "COD",
            Order.status == OrderStatus.DELIVERED,
            Order.created_at < datetime.combine(resolved_from, datetime.min.time()),
            *additional_filters
        ))
    )).scalar_one()

    opening_revenue = _to_float(float(opening_revenue_sum) + float(opening_cod_sum) * 0.05)

    opening_expense_sum = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(
            Expense.expense_date < resolved_from,
            Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
        ))
    )).scalar_one()
    opening_expenses = _to_float(opening_expense_sum)
    opening_profit = _to_float(opening_revenue - opening_expenses)

    # Calculate actual values in date range
    filters_orders = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    revenue_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(*filters_orders))
    )).scalar_one()
    
    cod_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.cod_amount), 0))
        .where(and_(
            Order.payment_method == "COD",
            Order.status == OrderStatus.DELIVERED,
            *filters_orders
        ))
    )).scalar_one()
    
    total_revenue = _to_float(float(revenue_sum) + float(cod_sum) * 0.05)
    
    filters_exp = []
    if scoped_franchise_id:
        filters_exp.append(Expense.franchise_id == scoped_franchise_id)
    filters_exp.append(Expense.expense_date >= resolved_from)
    filters_exp.append(Expense.expense_date <= resolved_to)
        
    expense_sum = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(*filters_exp))
    )).scalar_one()
    
    total_expenses = _to_float(expense_sum)
    net_profit = _to_float(total_revenue - total_expenses)
    
    items = [{
        "revenue": total_revenue,
        "expenses": total_expenses,
        "net_profit": net_profit
    }]

    return {
        "report": "Profit & Loss Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_revenue": opening_revenue,
        "opening_expenses": opening_expenses,
        "opening_profit": opening_profit,
        "items": items,
        "totals": {
            "revenue": total_revenue,
            "expenses": total_expenses,
            "net_profit": net_profit
        }
    }


async def hsn_summary_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_revenue = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.shipping_charge, additional_filters
    )

    filters = _order_filters(scoped_franchise_id, resolved_from, resolved_to)
    revenue_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(*filters))
    )).scalar_one()
    
    taxable = _to_float(revenue_sum)
    gst = _to_float(taxable * 0.18)
    
    items = [{
        "hsn_code": "996812",
        "taxable_amount": taxable,
        "gst_amount": gst
    }]

    return {
        "report": "HSN Summary Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_taxable_amount": opening_revenue,
        "opening_gst_amount": _to_float(opening_revenue * 0.18),
        "items": items,
        "totals": {
            "taxable_amount": _to_float(opening_revenue + taxable),
            "gst_amount": _to_float((opening_revenue * 0.18) + gst)
        }
    }


async def gst_collection_summary(
    db: AsyncSession,
    current_user: User,
    year: int | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_year = year or date.today().year

    start_of_year = datetime(target_year, 1, 1)
    
    # Calculate opening values before target year
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    opening_rev = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(
            Order.created_at < start_of_year,
            *additional_filters
        ))
    )).scalar_one()

    additional_filters_exp = []
    if scoped_franchise_id:
        additional_filters_exp.append(Expense.franchise_id == scoped_franchise_id)

    opening_exp = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(
            Expense.expense_date < start_of_year.date(),
            *additional_filters_exp
        ))
    )).scalar_one()

    opening_collected = _to_float(float(opening_rev) * 0.18)
    opening_paid = _to_float(float(opening_exp) * 0.18)
    opening_balance = _to_float(opening_collected - opening_paid)

    items = []
    for month in range(1, 13):
        start = datetime(target_year, month, 1)
        end = datetime(target_year, month, calendar.monthrange(target_year, month)[1], 23, 59, 59)
        
        filters = [Order.created_at >= start, Order.created_at <= end]
        if scoped_franchise_id:
            filters.append(Order.franchise_id == scoped_franchise_id)
        revenue = (await db.execute(select(func.coalesce(func.sum(Order.shipping_charge), 0)).where(and_(*filters)))).scalar_one()
        collected_gst = _to_float(float(revenue) * 0.18)
        
        filters_exp = [Expense.expense_date >= start.date(), Expense.expense_date <= end.date()]
        if scoped_franchise_id:
            filters_exp.append(Expense.franchise_id == scoped_franchise_id)
        exp_sum = (await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(*filters_exp)))).scalar_one()
        paid_gst = _to_float(float(exp_sum) * 0.18)
        
        items.append({
            "month": calendar.month_name[month],
            "collected_gst": collected_gst,
            "paid_gst": paid_gst,
            "balance": _to_float(collected_gst - paid_gst)
        })

    total_collected = _to_float(sum(item["collected_gst"] for item in items))
    total_paid = _to_float(sum(item["paid_gst"] for item in items))
    total_balance = _to_float(sum(item["balance"] for item in items))

    return {
        "report": "GST Collection Summary",
        "year": target_year,
        "opening_collected_gst": opening_collected,
        "opening_paid_gst": opening_paid,
        "opening_balance": opening_balance,
        "items": items,
        "totals": {
            "collected_gst": _to_float(float(opening_collected) + float(total_collected)),
            "paid_gst": _to_float(float(opening_paid) + float(total_paid)),
            "balance": _to_float(float(opening_balance) + float(total_balance))
        }
    }


async def franchise_outstanding_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = [Invoice.status == "pending"]
    if scoped_franchise_id:
        additional_filters.append(Invoice.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_pending = await _resolve_dates_and_opening(
        db, Invoice, Invoice.created_at, date_from, date_to, Invoice.total_amount, additional_filters
    )

    filters = [
        Invoice.status == "pending",
        Invoice.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Invoice.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
        
    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.desc()))).scalars().all()
    items = [
        {
            "franchise": inv.franchise.name if inv.franchise else inv.franchise_id,
            "pending_amount": _to_float(inv.total_amount),
            "due_date": (inv.created_at + timedelta(days=15)).strftime("%Y-%m-%d"),
            "status": "Overdue" if (datetime.utcnow() > inv.created_at + timedelta(days=15)) else "Pending"
        }
        for inv in invoices
    ]
    total_pending = _to_float(sum(item["pending_amount"] for item in items))

    return {
        "report": "Franchise Outstanding Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_pending_amount": opening_pending,
        "items": items,
        "totals": {
            "pending_amount": _to_float(float(opening_pending) + float(total_pending))
        }
    }


async def franchise_collection_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    # Resolve dates
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Franchise, Franchise.created_at, date_from, date_to, None, []
    )

    filters = []
    if scoped_franchise_id:
        filters.append(Franchise.id == scoped_franchise_id)
    franchises = (await db.execute(select(Franchise).where(and_(*filters)))).scalars().all()
    
    items = []
    total_cash_opening = 0.0
    total_bank_opening = 0.0
    total_exp_opening = 0.0

    for f in franchises:
        # Opening collection Split
        opening_cash = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                CashVoucher.payment_mode.ilike("%cash%"),
                CashVoucher.voucher_date < resolved_from
            ))
        )).scalar_one()

        opening_bank = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                ~CashVoucher.payment_mode.ilike("%cash%"),
                CashVoucher.voucher_date < resolved_from
            ))
        )).scalar_one()

        opening_exp = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(and_(
                Expense.franchise_id == f.id,
                Expense.expense_date < resolved_from
            ))
        )).scalar_one()

        total_cash_opening += float(opening_cash)
        total_bank_opening += float(opening_bank)
        total_exp_opening += float(opening_exp)

        # Range Collections
        cash = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                CashVoucher.payment_mode.ilike("%cash%"),
                CashVoucher.voucher_date >= resolved_from,
                CashVoucher.voucher_date <= resolved_to
            ))
        )).scalar_one()
        
        bank = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                ~CashVoucher.payment_mode.ilike("%cash%"),
                CashVoucher.voucher_date >= resolved_from,
                CashVoucher.voucher_date <= resolved_to
            ))
        )).scalar_one()
        
        expenses = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(and_(
                Expense.franchise_id == f.id,
                Expense.expense_date >= resolved_from,
                Expense.expense_date <= resolved_to
            ))
        )).scalar_one()
        
        items.append({
            "franchise": f.name,
            "cash_collection": _to_float(cash),
            "bank_deposit": _to_float(bank),
            "closing_balance": _to_float(float(cash) + float(bank) - float(expenses))
        })

    total_cash = _to_float(sum(item["cash_collection"] for item in items))
    total_bank = _to_float(sum(item["bank_deposit"] for item in items))
    total_closing = _to_float(sum(item["closing_balance"] for item in items))

    opening_balance_val = _to_float(total_cash_opening + total_bank_opening - total_exp_opening)

    return {
        "report": "Franchise Collection Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_cash_collection": _to_float(total_cash_opening),
        "opening_bank_deposit": _to_float(total_bank_opening),
        "opening_balance": opening_balance_val,
        "items": items,
        "totals": {
            "cash_collection": _to_float(float(total_cash_opening) + float(total_cash)),
            "bank_deposit": _to_float(float(total_bank_opening) + float(total_bank)),
            "closing_balance": _to_float(float(opening_balance_val) + float(total_closing))
        }
    }


async def franchise_profitability_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    # Resolve dates
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Franchise, Franchise.created_at, date_from, date_to, None, []
    )

    filters = []
    if scoped_franchise_id:
        filters.append(Franchise.id == scoped_franchise_id)
    franchises = (await db.execute(select(Franchise).where(and_(*filters)))).scalars().all()
    
    items = []
    total_rev_opening = 0.0
    total_exp_opening = 0.0

    for f in franchises:
        # Opening values
        rev_opening = (await db.execute(
            select(func.coalesce(func.sum(Order.shipping_charge), 0))
            .where(and_(
                Order.franchise_id == f.id,
                Order.created_at < datetime.combine(resolved_from, datetime.min.time())
            ))
        )).scalar_one()

        exp_opening = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(and_(
                Expense.franchise_id == f.id,
                Expense.expense_date < resolved_from
            ))
        )).scalar_one()

        total_rev_opening += float(rev_opening) * 0.3
        total_exp_opening += float(exp_opening)

        # Range values
        revenue_sum = (await db.execute(
            select(func.coalesce(func.sum(Order.shipping_charge), 0))
            .where(and_(
                Order.franchise_id == f.id,
                Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
                Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
            ))
        )).scalar_one()
        
        revenue = _to_float(float(revenue_sum) * 0.3)
        
        expenses = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(and_(
                Expense.franchise_id == f.id,
                Expense.expense_date >= resolved_from,
                Expense.expense_date <= resolved_to
            ))
        )).scalar_one()
        
        items.append({
            "franchise": f.name,
            "revenue": revenue,
            "expenses": _to_float(expenses),
            "profit": _to_float(revenue - float(expenses))
        })

    total_revenue = _to_float(sum(item["revenue"] for item in items))
    total_expenses = _to_float(sum(item["expenses"] for item in items))
    total_profit = _to_float(sum(item["profit"] for item in items))

    opening_rev_val = _to_float(total_rev_opening)
    opening_exp_val = _to_float(total_exp_opening)
    opening_profit_val = _to_float(opening_rev_val - opening_exp_val)

    return {
        "report": "Franchise Profitability Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_revenue": opening_rev_val,
        "opening_expenses": opening_exp_val,
        "opening_profit": opening_profit_val,
        "items": items,
        "totals": {
            "revenue": _to_float(float(opening_rev_val) + float(total_revenue)),
            "expenses": _to_float(float(opening_exp_val) + float(total_expenses)),
            "profit": _to_float(float(opening_profit_val) + float(total_profit))
        }
    }


async def area_wise_business_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    additional_filters = []
    if scoped_franchise_id:
        additional_filters.append(Order.franchise_id == scoped_franchise_id)

    resolved_from, resolved_to, opening_revenue = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, Order.shipping_charge, additional_filters
    )

    filters = [
        Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
        Order.created_at <= datetime.combine(resolved_to, datetime.max.time())
    ]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
        
    rows = (await db.execute(
        select(
            Consignee.city,
            func.count(Order.id),
            func.coalesce(func.sum(Order.shipping_charge), 0)
        )
        .join(Consignee, Order.consignee_id == Consignee.id)
        .where(and_(*filters))
        .group_by(Consignee.city)
        .order_by(func.count(Order.id).desc())
    )).all()
    
    items = []
    for row in rows:
        city = row[0]
        shipments = row[1]
        revenue = _to_float(row[2])
        
        pending = (await db.execute(
            select(func.count(Order.id))
            .join(Consignee, Order.consignee_id == Consignee.id)
            .where(and_(
                Consignee.city == city,
                Order.status.notin_([OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST]),
                *filters
            ))
        )).scalar_one()
        
        items.append({
            "area": city or "Unknown",
            "shipments": shipments,
            "revenue": revenue,
            "pending_deliveries": pending
        })
        
    total_shipments = sum(item["shipments"] for item in items)
    total_revenue = _to_float(sum(item["revenue"] for item in items))
    total_pending = sum(item["pending_deliveries"] for item in items)

    return {
        "report": "Area Wise Business Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "opening_revenue": opening_revenue,
        "items": items,
        "totals": {
            "shipments": total_shipments,
            "revenue": _to_float(float(opening_revenue) + float(total_revenue)),
            "pending_deliveries": total_pending
        }
    }


async def performance_dashboard_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    # We resolve dates
    resolved_from, resolved_to, _ = await _resolve_dates_and_opening(
        db, Order, Order.created_at, date_from, date_to, None, []
    )
    
    parameters = ["Bookings", "Revenue", "Expenses"]
    items = []
    for param in parameters:
        curr_val = 0.0
        prev_val = 0.0
        
        if param == "Bookings":
            curr_val = float((await db.execute(
                select(func.count(Order.id))
                .where(and_(
                    Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
                    Order.created_at <= datetime.combine(resolved_to, datetime.max.time()),
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            # Previous same length duration:
            duration = resolved_to - resolved_from
            prev_to = resolved_from - timedelta(days=1)
            prev_from = prev_to - duration
            prev_val = float((await db.execute(
                select(func.count(Order.id))
                .where(and_(
                    Order.created_at >= datetime.combine(prev_from, datetime.min.time()),
                    Order.created_at <= datetime.combine(prev_to, datetime.max.time()),
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
        elif param == "Revenue":
            curr_val = float((await db.execute(
                select(func.coalesce(func.sum(Order.shipping_charge), 0))
                .where(and_(
                    Order.created_at >= datetime.combine(resolved_from, datetime.min.time()),
                    Order.created_at <= datetime.combine(resolved_to, datetime.max.time()),
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            duration = resolved_to - resolved_from
            prev_to = resolved_from - timedelta(days=1)
            prev_from = prev_to - duration
            prev_val = float((await db.execute(
                select(func.coalesce(func.sum(Order.shipping_charge), 0))
                .where(and_(
                    Order.created_at >= datetime.combine(prev_from, datetime.min.time()),
                    Order.created_at <= datetime.combine(prev_to, datetime.max.time()),
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
        elif param == "Expenses":
            curr_val = float((await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0))
                .where(and_(
                    Expense.expense_date >= resolved_from,
                    Expense.expense_date <= resolved_to,
                    Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            duration = resolved_to - resolved_from
            prev_to = resolved_from - timedelta(days=1)
            prev_from = prev_to - duration
            prev_val = float((await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0))
                .where(and_(
                    Expense.expense_date >= prev_from,
                    Expense.expense_date <= prev_to,
                    Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            
        growth = 0.0
        if prev_val > 0:
            growth = round(((curr_val - prev_val) / prev_val) * 100, 2)
            
        items.append({
            "parameter": param,
            "current_month": _to_float(curr_val),
            "previous_month": _to_float(prev_val),
            "growth_percent": growth
        })
        
    return {
        "report": "Performance Dashboard Report",
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": items
    }

