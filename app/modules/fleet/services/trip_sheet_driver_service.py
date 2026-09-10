from datetime import date, datetime, time, timedelta
from typing import Any
from types import SimpleNamespace

import pytz
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.schemas.trip_sheet_driver import TripRespondRequest
from app.modules.fleet.services.driver_assignment_runtime_service import (
    export_assignment_order_history,
    list_active_assignment_trips,
    list_assignment_order_history,
    list_new_assignment_trips,
    resolve_open_work,
    respond_to_assignment,
)

IST = pytz.timezone("Asia/Kolkata")
EXPORT_RANGES = frozenset({"this_week", "this_month", "last_month", "all"})
EXPORT_ROW_CAP = 5000
DRIVER_TRIP_HISTORY_REPORT = "Driver Trip History Report"


async def list_new_trips(db: AsyncSession, driver: Driver) -> list:
    return await list_new_assignment_trips(db, driver)


async def list_active_trips(db: AsyncSession, driver: Driver) -> list:
    return await list_active_assignment_trips(db, driver)


async def respond_to_sheet(
    db: AsyncSession, driver: Driver, trip_sheet_id: str, payload: TripRespondRequest
) -> dict:
    # Compat: trip_sheet_id path param is the assignment id for mobile.
    return await respond_to_assignment(db, driver, trip_sheet_id, payload)


async def get_order_on_driver_sheet(db: AsyncSession, driver: Driver, order_id: str):
    """Compat shim for scan/etc.: returns (fake_sheet, order) from open assignment."""
    _kind, assignment, order = await resolve_open_work(db, driver, order_id)
    return SimpleNamespace(id=assignment.id, driver_status=assignment.status, orders=[]), order


async def list_order_history(
    db: AsyncSession, driver: Driver, page: int, limit: int
) -> dict:
    return await list_assignment_order_history(db, driver, page, limit)


def _ist_day_start(d: date) -> datetime:
    return IST.localize(datetime.combine(d, time.min)).replace(tzinfo=None)


def _ist_day_end(d: date) -> datetime:
    return IST.localize(datetime.combine(d, time.max)).replace(tzinfo=None)


def _ist_now() -> datetime:
    return datetime.now(IST)


def resolve_export_date_range(
    range_value: str | None,
    start_date: date | None,
    end_date: date | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None, date | None, date | None]:
    """Resolve inclusive IST bounds for Order.updated_at.

    Custom start+end win over range. Both custom dates required together.
    range required when custom dates absent. Returns (start_dt, end_dt, date_from, date_to);
    both datetimes None means no date filter (`all`).
    """
    has_start = start_date is not None
    has_end = end_date is not None
    if has_start != has_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="startDate and endDate must both be provided together",
        )
    if has_start and has_end:
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="startDate must be on or before endDate",
            )
        return _ist_day_start(start_date), _ist_day_end(end_date), start_date, end_date

    if not range_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range is required when startDate and endDate are not provided",
        )
    if range_value not in EXPORT_RANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"range must be one of: {', '.join(sorted(EXPORT_RANGES))}",
        )
    if range_value == "all":
        return None, None, None, None

    if now is None:
        ist_now = _ist_now()
    elif now.tzinfo is None:
        ist_now = IST.localize(now)
    else:
        ist_now = now.astimezone(IST)
    today = ist_now.date()

    if range_value == "this_week":
        # Monday start (ISO weekday 0 = Monday)
        week_start = today - timedelta(days=today.weekday())
        return _ist_day_start(week_start), _ist_day_end(today), week_start, today

    if range_value == "this_month":
        month_start = today.replace(day=1)
        return _ist_day_start(month_start), _ist_day_end(today), month_start, today

    # last_month
    first_this_month = today.replace(day=1)
    last_month_end = first_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return (
        _ist_day_start(last_month_start),
        _ist_day_end(last_month_end),
        last_month_start,
        last_month_end,
    )


def _format_address(loc: Any) -> str:
    if not loc:
        return ""
    return ", ".join(
        p
        for p in [
            getattr(loc, "address_line_1", None),
            getattr(loc, "address_line_2", None),
            getattr(loc, "city", None),
            getattr(loc, "pincode", None),
        ]
        if p
    )


def _to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return IST.localize(dt)
    return dt.astimezone(IST)


def _map_trip_status(order_status: str | None) -> str:
    s = (order_status or "").strip()
    lower = s.lower()
    if lower == "delivered":
        return "Completed"
    if lower == "cancelled":
        return "Cancelled"
    if lower in {"returned", "rto_delivered"}:
        return "Returned"
    return s


def _order_to_export_row(order: Order) -> dict:
    updated = order.updated_at
    ist_dt = _to_ist(updated) if updated else None
    pickup = order.pickup_address
    consignee = order.consignee
    payment_method = (order.payment_method or "").upper()
    payment_status = "PAID" if (order.payment_method or "").lower() == "prepaid" else "PENDING"
    return {
        "trip_id": order.id,
        "order_id": order.order_number,
        "completed_date": ist_dt.strftime("%Y-%m-%d") if ist_dt else "",
        "completed_time": ist_dt.strftime("%H:%M") if ist_dt else "",
        "pickup_hub": (pickup.nickname if pickup else "") or "",
        "customer_name": (consignee.name if consignee else "") or "",
        "delivery_address": _format_address(consignee),
        "weight": float(order.total_weight_kg or 0),
        "earnings": float(order.total_freight or 0),
        "payment_status": payment_status,
        "payment_method": payment_method,
        "trip_status": _map_trip_status(order.status),
    }


async def export_order_history(
    db: AsyncSession,
    driver: Driver,
    range_value: str | None,
    start_date: date | None,
    end_date: date | None,
) -> dict:
    start_dt, end_dt, date_from, date_to = resolve_export_date_range(
        range_value, start_date, end_date
    )
    items = await export_assignment_order_history(
        db,
        driver,
        start_dt=start_dt,
        end_dt=end_dt,
        row_cap=EXPORT_ROW_CAP,
        order_to_row=_order_to_export_row,
    )
    report: dict[str, Any] = {
        "report": DRIVER_TRIP_HISTORY_REPORT,
        "items": items,
    }
    if date_from is not None and date_to is not None:
        report["date_from"] = date_from.isoformat()
        report["date_to"] = date_to.isoformat()
    return report
