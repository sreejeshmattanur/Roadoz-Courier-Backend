import calendar
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
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
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_date = report_date or date.today()
    filters = _order_filters(scoped_franchise_id, target_date, target_date)

    result = await db.execute(
        select(Order)
        .where(and_(*filters))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    return {
        "report": "Daily Booking Report",
        "date": target_date,
        "total_bookings": len(orders),
        "total_amount": _to_float(sum(float(order.shipping_charge or 0) for order in orders)),
        "items": [
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
        ],
    }


async def customer_wise_booking_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)

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

    return {
        "report": "Customer Wise Booking Report",
        "date_from": date_from,
        "date_to": date_to,
        "items": [
            {
                "customer": row[0],
                "bookings": row[1],
                "revenue": _to_float(row[2]),
                "pending_amount": _to_float(row[3]),
            }
            for row in rows
        ],
    }


async def service_type_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)
    rows = (
        await db.execute(
            select(Order.order_type, func.count(Order.id), func.coalesce(func.sum(Order.shipping_charge), 0))
            .where(and_(*filters))
            .group_by(Order.order_type)
        )
    ).all()
    return {
        "report": "Service Type Report",
        "items": [
            {"service_type": row[0], "total_bookings": row[1], "revenue": _to_float(row[2])}
            for row in rows
        ],
    }


async def delivery_status_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)
    result = await db.execute(select(Order).where(and_(*filters)).order_by(Order.updated_at.desc()))
    orders = result.scalars().all()
    return {
        "report": "Delivery Status Report",
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


async def pending_delivery_report(db: AsyncSession, current_user: User, franchise_id: str | None = None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    terminal_statuses = [OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST]
    filters = [Order.status.notin_(terminal_statuses)]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    result = await db.execute(select(Order).where(and_(*filters)).order_by(Order.created_at.asc()))
    orders = result.scalars().all()
    today = datetime.utcnow().date()
    return {
        "report": "Pending Delivery Report",
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


async def cod_pending_report(db: AsyncSession, current_user: User, franchise_id: str | None = None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [
        Order.payment_method == "COD",
        Order.cod_amount.is_not(None),
        ~Order.id.in_(select(RemittanceOrder.order_id)),
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
    return {
        "report": "COD Pending Report",
        "total_pending_amount": _to_float(sum(float(row[0].cod_amount or 0) for row in rows)),
        "items": [
            {
                "booking_no": order.order_number,
                "merchant": franchise_name or order.franchise_id,
                "pending_amount": _to_float(order.cod_amount),
                "status": _status_value(order.status),
            }
            for order, franchise_name in rows
        ],
    }


async def gst_sales_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    start, end = _date_range(date_from, date_to)
    filters = []
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
    if start:
        filters.append(Invoice.created_at >= start)
    if end:
        filters.append(Invoice.created_at <= end)

    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.desc()))).scalars().all()
    return {
        "report": "GST Sales Report",
        "total_taxable_amount": _to_float(sum(float(invoice.subtotal or 0) for invoice in invoices)),
        "total_gst": _to_float(sum(float(invoice.tax_amount or 0) for invoice in invoices)),
        "total": _to_float(sum(float(invoice.total_amount or 0) for invoice in invoices)),
        "items": [
            {
                "invoice_no": invoice.invoice_number,
                "taxable_amount": _to_float(invoice.subtotal),
                "cgst": _to_float(float(invoice.tax_amount or 0) / 2),
                "sgst": _to_float(float(invoice.tax_amount or 0) / 2),
                "igst": 0.0,
                "total": _to_float(invoice.total_amount),
            }
            for invoice in invoices
        ],
    }


async def franchise_settlement_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)
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
    return {"report": "Franchise Settlement Report", "items": items}


async def monthly_revenue_analysis(db: AsyncSession, current_user: User, year: int | None = None, franchise_id: str | None = None) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_year = year or date.today().year
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
    return {"report": "Monthly Revenue Analysis", "year": target_year, "items": items}


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
    return data


async def delivery_efficiency_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)
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
    return {"report": "Delivery Efficiency Report", "items": list(grouped.values())}


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
    closing_balance = _to_float(opening_balance + total_collection - total_expenses)
    
    return {
        "report": "Day Close Report",
        "date": target_date,
        "items": [{
            "opening_balance": opening_balance,
            "collection": total_collection,
            "expenses": total_expenses,
            "closing_balance": closing_balance
        }]
    }


async def branch_activity_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    franchises = (await db.execute(select(Franchise))).scalars().all()
    items = []
    for f in franchises:
        bookings = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                *_order_filters(None, date_from, date_to)[1:]
            ))
        )).scalar_one()
        
        deliveries = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                Order.status == OrderStatus.DELIVERED,
                *_order_filters(None, date_from, date_to)[1:]
            ))
        )).scalar_one()
        
        terminal_statuses = [OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST]
        pending = (await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.franchise_id == f.id,
                Order.status.notin_(terminal_statuses),
                *_order_filters(None, date_from, date_to)[1:]
            ))
        )).scalar_one()
        
        collections = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                CashVoucher.voucher_date >= date_from if date_from else True,
                CashVoucher.voucher_date <= date_to if date_to else True
            ))
        )).scalar_one()
        
        items.append({
            "branch": f.name,
            "bookings": bookings,
            "deliveries": deliveries,
            "collections": _to_float(collections),
            "pending": pending
        })
        
    return {
        "report": "Branch Activity Report",
        "items": items
    }


async def user_activity_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    users = (await db.execute(select(User))).scalars().all()
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
                Order.created_at >= datetime.combine(date_from, datetime.min.time()) if date_from else True,
                Order.created_at <= datetime.combine(date_to, datetime.max.time()) if date_to else True
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
    filters = [Order.status.in_([OrderStatus.RETURNED, OrderStatus.RTO_DELIVERED, OrderStatus.RTO_IN_TRANSIT])]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(Order.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        filters.append(Order.created_at <= datetime.combine(date_to, datetime.max.time()))
        
    orders = (await db.execute(select(Order).where(and_(*filters)).order_by(Order.updated_at.desc()))).scalars().all()
    return {
        "report": "Returned Shipment Report",
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
    filters = [CashVoucher.type == "receipt"]
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(CashVoucher.voucher_date >= date_from)
    if date_to:
        filters.append(CashVoucher.voucher_date <= date_to)
        
    vouchers = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.desc()))).scalars().all()
    return {
        "report": "Collection Summary Report",
        "items": [
            {
                "receipt_no": v.voucher_no,
                "customer": v.franchise.name if v.franchise else "Walk-in Customer",
                "amount": _to_float(v.amount),
                "payment_mode": v.payment_mode
            }
            for v in vouchers
        ]
    }


async def outstanding_collection_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [Invoice.status == "pending"]
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.asc()))).scalars().all()
    return {
        "report": "Outstanding Collection Report",
        "items": [
            {
                "customer": inv.franchise.name if inv.franchise else inv.franchise_id,
                "invoice": inv.invoice_number,
                "balance": _to_float(inv.total_amount),
                "due_date": (inv.created_at + timedelta(days=15)).date()
            }
            for inv in invoices
        ]
    }


async def daily_collection_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [CashVoucher.type == "receipt"]
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(CashVoucher.voucher_date >= date_from)
    if date_to:
        filters.append(CashVoucher.voucher_date <= date_to)
        
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
        
    return {
        "report": "Daily Collection Report",
        "items": sorted(grouped.values(), key=lambda r: r["date"], reverse=True)
    }


async def cod_settlement_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
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
    return {
        "report": "COD Settlement Report",
        "items": items
    }


async def cod_commission_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [
        Order.payment_method == "COD",
        Order.status == OrderStatus.DELIVERED,
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
    
    return {
        "report": "COD Commission Report",
        "items": [
            {
                "merchant": row[0],
                "commission_percent": 5.0,
                "amount": _to_float(float(row[1]) * 0.05)
            }
            for row in rows
        ]
    }


async def cash_book_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(CashVoucher.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(CashVoucher.voucher_date >= date_from)
    if date_to:
        filters.append(CashVoucher.voucher_date <= date_to)
        
    vouchers = (await db.execute(select(CashVoucher).where(and_(*filters)).order_by(CashVoucher.voucher_date.asc()))).scalars().all()
    items = []
    balance = 0.0
    for v in vouchers:
        credit = float(v.amount) if v.type == "receipt" else 0.0
        debit = float(v.amount) if v.type == "payment" else 0.0
        balance += credit - debit
        items.append({
            "date": v.voucher_date.strftime("%Y-%m-%d"),
            "voucher_no": v.voucher_no,
            "debit": _to_float(debit),
            "credit": _to_float(credit),
            "balance": _to_float(balance)
        })
    return {
        "report": "Cash Book Report",
        "items": items
    }


async def expense_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(Expense.franchise_id == scoped_franchise_id)
    if date_from:
        filters.append(Expense.expense_date >= date_from)
    if date_to:
        filters.append(Expense.expense_date <= date_to)
        
    expenses = (await db.execute(select(Expense).where(and_(*filters)).order_by(Expense.expense_date.desc()))).scalars().all()
    return {
        "report": "Expense Report",
        "items": [
            {
                "expense_head": exp.expense_head,
                "amount": _to_float(exp.amount),
                "approved_by": exp.approved_by or "Super Admin"
            }
            for exp in expenses
        ]
    }


async def profit_loss_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    filters_orders = _order_filters(scoped_franchise_id, date_from, date_to)
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
    if date_from:
        filters_exp.append(Expense.expense_date >= date_from)
    if date_to:
        filters_exp.append(Expense.expense_date <= date_to)
        
    expense_sum = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(and_(*filters_exp))
    )).scalar_one()
    
    total_expenses = _to_float(expense_sum)
    net_profit = _to_float(total_revenue - total_expenses)
    
    return {
        "report": "Profit & Loss Report",
        "items": [{
            "revenue": total_revenue,
            "expenses": total_expenses,
            "net_profit": net_profit
        }]
    }


async def hsn_summary_report(
    db: AsyncSession,
    current_user: User,
    date_from: date | None = None,
    date_to: date | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = _order_filters(scoped_franchise_id, date_from, date_to)
    
    revenue_sum = (await db.execute(
        select(func.coalesce(func.sum(Order.shipping_charge), 0))
        .where(and_(*filters))
    )).scalar_one()
    
    taxable = _to_float(revenue_sum)
    gst = _to_float(taxable * 0.18)
    
    return {
        "report": "HSN Summary Report",
        "items": [{
            "hsn_code": "996812",
            "taxable_amount": taxable,
            "gst_amount": gst
        }]
    }


async def gst_collection_summary(
    db: AsyncSession,
    current_user: User,
    year: int | None = None,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    target_year = year or date.today().year
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
        
    return {
        "report": "GST Collection Summary",
        "items": items
    }


async def franchise_outstanding_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = [Invoice.status == "pending"]
    if scoped_franchise_id:
        filters.append(Invoice.franchise_id == scoped_franchise_id)
        
    invoices = (await db.execute(select(Invoice).where(and_(*filters)).order_by(Invoice.created_at.desc()))).scalars().all()
    return {
        "report": "Franchise Outstanding Report",
        "items": [
            {
                "franchise": inv.franchise.name if inv.franchise else inv.franchise_id,
                "pending_amount": _to_float(inv.total_amount),
                "due_date": (inv.created_at + timedelta(days=15)).strftime("%Y-%m-%d"),
                "status": "Overdue" if (datetime.utcnow() > inv.created_at + timedelta(days=15)) else "Pending"
            }
            for inv in invoices
        ]
    }


async def franchise_collection_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(Franchise.id == scoped_franchise_id)
    franchises = (await db.execute(select(Franchise).where(and_(*filters)))).scalars().all()
    
    items = []
    for f in franchises:
        cash = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                CashVoucher.payment_mode.ilike("%cash%")
            ))
        )).scalar_one()
        
        bank = (await db.execute(
            select(func.coalesce(func.sum(CashVoucher.amount), 0))
            .where(and_(
                CashVoucher.franchise_id == f.id,
                CashVoucher.type == "receipt",
                ~CashVoucher.payment_mode.ilike("%cash%")
            ))
        )).scalar_one()
        
        expenses = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.franchise_id == f.id)
        )).scalar_one()
        
        items.append({
            "franchise": f.name,
            "cash_collection": _to_float(cash),
            "bank_deposit": _to_float(bank),
            "closing_balance": _to_float(float(cash) + float(bank) - float(expenses))
        })
        
    return {
        "report": "Franchise Collection Report",
        "items": items
    }


async def franchise_profitability_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
    if scoped_franchise_id:
        filters.append(Franchise.id == scoped_franchise_id)
    franchises = (await db.execute(select(Franchise).where(and_(*filters)))).scalars().all()
    
    items = []
    for f in franchises:
        revenue_sum = (await db.execute(
            select(func.coalesce(func.sum(Order.shipping_charge), 0))
            .where(Order.franchise_id == f.id)
        )).scalar_one()
        
        revenue = _to_float(float(revenue_sum) * 0.3)
        
        expenses = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.franchise_id == f.id)
        )).scalar_one()
        
        items.append({
            "franchise": f.name,
            "revenue": revenue,
            "expenses": _to_float(expenses),
            "profit": _to_float(revenue - float(expenses))
        })
        
    return {
        "report": "Franchise Profitability Report",
        "items": items
    }


async def area_wise_business_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    filters = []
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
        
    return {
        "report": "Area Wise Business Report",
        "items": items
    }


async def performance_dashboard_report(
    db: AsyncSession,
    current_user: User,
    franchise_id: str | None = None,
) -> dict:
    scoped_franchise_id = await _scope_franchise_id(db, current_user, franchise_id)
    
    today = datetime.utcnow()
    this_month_start = datetime(today.year, today.month, 1)
    first_of_this_month = today.replace(day=1)
    prev_month_end = first_of_this_month - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    
    parameters = ["Bookings", "Revenue", "Expenses"]
    items = []
    for param in parameters:
        curr_val = 0.0
        prev_val = 0.0
        
        if param == "Bookings":
            curr_val = float((await db.execute(
                select(func.count(Order.id))
                .where(and_(
                    Order.created_at >= this_month_start,
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            prev_val = float((await db.execute(
                select(func.count(Order.id))
                .where(and_(
                    Order.created_at >= prev_month_start,
                    Order.created_at <= prev_month_end,
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
        elif param == "Revenue":
            curr_val = float((await db.execute(
                select(func.coalesce(func.sum(Order.shipping_charge), 0))
                .where(and_(
                    Order.created_at >= this_month_start,
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            prev_val = float((await db.execute(
                select(func.coalesce(func.sum(Order.shipping_charge), 0))
                .where(and_(
                    Order.created_at >= prev_month_start,
                    Order.created_at <= prev_month_end,
                    Order.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
        elif param == "Expenses":
            curr_val = float((await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0))
                .where(and_(
                    Expense.expense_date >= this_month_start.date(),
                    Expense.franchise_id == scoped_franchise_id if scoped_franchise_id else True
                ))
            )).scalar_one())
            prev_val = float((await db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0))
                .where(and_(
                    Expense.expense_date >= prev_month_start.date(),
                    Expense.expense_date <= prev_month_end.date(),
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
        "items": items
    }

