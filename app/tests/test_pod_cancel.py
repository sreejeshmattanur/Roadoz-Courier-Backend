"""Mobile POD (cancel) / confirm-delivery / pickup-OTP assignment tests."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.order import OrderStatus
from app.modules.fleet.schemas.trip_sheet_driver import (
    TripStatusUpdateRequest,
    VerifyDropRequest,
    VerifyPickupRequest,
)
from app.modules.fleet.services.driver_trip_execution_service import (
    update_order_status,
    verify_drop,
    verify_pickup,
)


def _order(**kwargs):
    defaults = {
        "id": "order-1",
        "order_number": "RZ-1",
        "status": "Ofd",
        "previous_status": None,
        "meta": None,
        "consignee": SimpleNamespace(name="Recv"),
        "payment_method": "Prepaid",
        "cod_amount": None,
        "to_pay_amount": None,
        "total_freight": 100,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _pickup_assignment(**kwargs):
    defaults = {
        "id": "pa-1",
        "status": "in_progress",
        "updated_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _delivery_assignment(**kwargs):
    defaults = {
        "id": "da-1",
        "status": "in_progress",
        "updated_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _driver():
    return SimpleNamespace(id="driver-1", user_id="user-1")


@pytest.mark.asyncio
async def test_cancel_pod_sets_cancelled_on_assignment_and_order():
    order = _order(status="Ofd")
    assignment = _delivery_assignment()
    db = AsyncMock()
    payload = TripStatusUpdateRequest(
        status="CANCELLED",
        reason="Customer unavailable",
        phase="DELIVERY",
        timestamp=datetime(2026, 8, 8, 0, 52, 0),
        location={"latitude": 10.0, "longitude": 76.0},
    )

    with patch(
        "app.modules.fleet.services.driver_trip_execution_service.resolve_open_work",
        AsyncMock(return_value=("delivery", assignment, order)),
    ):
        result = await update_order_status(db, _driver(), order.id, payload)

    assert order.status == OrderStatus.CANCELLED.value
    assert assignment.status == "cancelled"
    assert result["status"] == "CANCELLED"
    assert order.meta["cancellation"]["phase"] == "DELIVERY"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cancel_requires_reason():
    order = _order()
    db = AsyncMock()
    payload = TripStatusUpdateRequest(status="CANCELLED", phase="DELIVERY", reason=None)

    with patch(
        "app.modules.fleet.services.driver_trip_execution_service.resolve_open_work",
        AsyncMock(return_value=("delivery", _delivery_assignment(), order)),
    ):
        with pytest.raises(HTTPException) as exc:
            await update_order_status(db, _driver(), order.id, payload)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_intermediate_status_rejected():
    with patch(
        "app.modules.fleet.services.driver_trip_execution_service.resolve_open_work",
        AsyncMock(return_value=("delivery", _delivery_assignment(), _order())),
    ):
        with pytest.raises(HTTPException) as exc:
            await update_order_status(
                AsyncMock(),
                _driver(),
                "order-1",
                TripStatusUpdateRequest(status="IN_TRANSIT"),
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_pickup_sets_picked():
    order = _order(status="pickup_assigned")
    assignment = _pickup_assignment()
    db = AsyncMock()

    with patch(
        "app.modules.fleet.services.driver_trip_execution_service.resolve_open_work",
        AsyncMock(return_value=("pickup", assignment, order)),
    ):
        result = await verify_pickup(db, _driver(), order.id, VerifyPickupRequest())

    assert order.status == OrderStatus.PICKED.value
    assert assignment.status == "completed"
    assert result["status"] == "PICKUP_COMPLETED"


@pytest.mark.asyncio
async def test_confirm_delivery_sets_delivered():
    order = _order(status="Ofd")
    assignment = _delivery_assignment()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    with patch(
        "app.modules.fleet.services.driver_trip_execution_service.resolve_open_work",
        AsyncMock(return_value=("delivery", assignment, order)),
    ):
        result = await verify_drop(
            db,
            _driver(),
            order.id,
            VerifyDropRequest(receiverName="A", signatureUrl="https://sig"),
        )

    assert order.status == OrderStatus.DELIVERED.value
    assert assignment.status == "completed"
    assert result["status"] == "DELIVERY_COMPLETED"
    assert result["paymentRequired"] is False
    db.add.assert_called()
