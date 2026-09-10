"""Driver dashboard HomeScreen summary tests."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.fleet.services.driver_dashboard_service import (
    _completion_percentage,
    _hourly_breakdown,
    get_driver_dashboard,
)


def test_completion_percentage_empty():
    assert _completion_percentage(0, 0, 0, 0) == 0


def test_completion_percentage_pickups_only():
    assert _completion_percentage(4, 5, 0, 0) == 80


def test_completion_percentage_deliveries_only():
    assert _completion_percentage(0, 0, 12, 15) == 80


def test_completion_percentage_mixed():
    assert _completion_percentage(4, 5, 12, 15) == 80


def test_hourly_breakdown_empty():
    rows = _hourly_breakdown([])
    assert len(rows) == 7
    assert [r["hour"] for r in rows] == ["8AM", "10AM", "12PM", "2PM", "4PM", "6PM", "8PM"]
    assert all(r["value"] == 0 for r in rows)


def test_hourly_breakdown_scales_to_peak():
    # two at 9:00 (8AM slot), one at 15:00 (2PM slot) → values 100 and 50
    rows = _hourly_breakdown(
        [
            datetime(2026, 8, 9, 9, 0, 0),
            datetime(2026, 8, 9, 9, 30, 0),
            datetime(2026, 8, 9, 15, 0, 0),
        ]
    )
    by_hour = {r["hour"]: r["value"] for r in rows}
    assert by_hour["8AM"] == 100
    assert by_hour["2PM"] == 50
    assert by_hour["10AM"] == 0


def _count_result(n: int):
    m = MagicMock()
    m.scalar_one.return_value = n
    return m


def _updated_ats(dts: list[datetime]):
    m = MagicMock()
    m.scalars.return_value.all.return_value = dts
    return m


@pytest.mark.asyncio
async def test_get_driver_dashboard_empty_day():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _count_result(0),
            _updated_ats([]),
            _count_result(0),
            _updated_ats([]),
        ]
    )
    driver = SimpleNamespace(id="driver-1")
    data = await get_driver_dashboard(db, driver, now=datetime(2026, 8, 9, 12, 0, 0))

    assert data["wallet"] == {"balance": 0, "currency": "INR"}
    assert data["todaysEarnings"] == {"amount": 0, "currency": "INR"}
    assert data["todaysPickups"] == {"completed": 0, "total": 0}
    assert data["todaysDeliveries"] == {"completed": 0, "total": 0}
    assert data["dailyGoal"]["completionPercentage"] == 0
    assert all(r["value"] == 0 for r in data["dailyGoal"]["hourlyBreakdown"])


@pytest.mark.asyncio
async def test_get_driver_dashboard_pickups_only():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _count_result(5),
            _updated_ats([datetime(2026, 8, 9, 9, 0, 0)] * 4),
            _count_result(0),
            _updated_ats([]),
        ]
    )
    data = await get_driver_dashboard(
        db, SimpleNamespace(id="driver-1"), now=datetime(2026, 8, 9, 12, 0, 0)
    )
    assert data["todaysPickups"] == {"completed": 4, "total": 5}
    assert data["todaysDeliveries"] == {"completed": 0, "total": 0}
    assert data["dailyGoal"]["completionPercentage"] == 80
    assert data["wallet"]["balance"] == 0
    assert data["todaysEarnings"]["amount"] == 0
