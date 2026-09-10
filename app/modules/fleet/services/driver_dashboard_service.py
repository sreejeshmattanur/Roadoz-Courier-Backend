"""Driver HomeScreen dashboard summary."""
from __future__ import annotations

from datetime import date, datetime, time

import pytz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery_assignment import DeliveryAssignment
from app.models.pickup_assignment import PickupAssignment
from app.modules.fleet.models.driver import Driver

IST = pytz.timezone("Asia/Kolkata")

# Spec labels: 8AM, 10AM, 12PM, 2PM, 4PM, 6PM, 8PM — each covers a 2h window.
HOURLY_SLOTS: tuple[tuple[str, int, int], ...] = (
    ("8AM", 8, 10),
    ("10AM", 10, 12),
    ("12PM", 12, 14),
    ("2PM", 14, 16),
    ("4PM", 16, 18),
    ("6PM", 18, 20),
    ("8PM", 20, 22),
)


def _ist_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime, date]:
    if now is None:
        ist_now = datetime.now(IST)
    elif now.tzinfo is None:
        ist_now = IST.localize(now)
    else:
        ist_now = now.astimezone(IST)
    today = ist_now.date()
    start = IST.localize(datetime.combine(today, time.min)).replace(tzinfo=None)
    end = IST.localize(datetime.combine(today, time.max)).replace(tzinfo=None)
    return start, end, today


def _to_ist_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(IST).replace(tzinfo=None)


def _slot_index(hour: int) -> int | None:
    for i, (_label, start_h, end_h) in enumerate(HOURLY_SLOTS):
        if start_h <= hour < end_h:
            return i
    return None


def _completion_percentage(
    pickups_done: int, pickups_total: int, deliveries_done: int, deliveries_total: int
) -> int:
    denom = pickups_total + deliveries_total
    if denom == 0:
        return 0
    return round(100 * (pickups_done + deliveries_done) / denom)


def _hourly_breakdown(completed_at: list[datetime]) -> list[dict]:
    counts = [0] * len(HOURLY_SLOTS)
    for dt in completed_at:
        naive = _to_ist_naive(dt)
        idx = _slot_index(naive.hour)
        if idx is not None:
            counts[idx] += 1
    peak = max(counts) if counts else 0
    return [
        {
            "hour": label,
            "value": 0 if peak == 0 else round(100 * counts[i] / peak),
        }
        for i, (label, _a, _b) in enumerate(HOURLY_SLOTS)
    ]


async def _assignment_counts(
    db: AsyncSession,
    *,
    model,
    driver_id: str,
    day_start: datetime,
    day_end: datetime,
) -> tuple[int, int, list[datetime]]:
    total = (
        await db.execute(
            select(func.count())
            .select_from(model)
            .where(
                model.driver_id == driver_id,
                model.created_at >= day_start,
                model.created_at <= day_end,
                model.status != "cancelled",
            )
        )
    ).scalar_one()

    completed_rows = (
        await db.execute(
            select(model.updated_at).where(
                model.driver_id == driver_id,
                model.status == "completed",
                model.updated_at >= day_start,
                model.updated_at <= day_end,
            )
        )
    ).scalars().all()

    return int(total or 0), len(completed_rows), list(completed_rows)


async def get_driver_dashboard(
    db: AsyncSession, driver: Driver, *, now: datetime | None = None
) -> dict:
    day_start, day_end, _today = _ist_day_bounds(now)

    pickups_total, pickups_done, pickup_times = await _assignment_counts(
        db,
        model=PickupAssignment,
        driver_id=driver.id,
        day_start=day_start,
        day_end=day_end,
    )
    deliveries_total, deliveries_done, delivery_times = await _assignment_counts(
        db,
        model=DeliveryAssignment,
        driver_id=driver.id,
        day_start=day_start,
        day_end=day_end,
    )

    return {
        "wallet": {"balance": 0, "currency": "INR"},
        "todaysEarnings": {"amount": 0, "currency": "INR"},
        "todaysDeliveries": {"completed": deliveries_done, "total": deliveries_total},
        "todaysPickups": {"completed": pickups_done, "total": pickups_total},
        "dailyGoal": {
            "completionPercentage": _completion_percentage(
                pickups_done, pickups_total, deliveries_done, deliveries_total
            ),
            "hourlyBreakdown": _hourly_breakdown(pickup_times + delivery_times),
        },
    }
