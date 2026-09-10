"""Driver trip execution — assignment-backed (confirm pickup, confirm delivery, POD=cancel).

Endpoint → mobile intent (URLs unchanged):
- POST .../verify-pickup → confirm pickup → Picked
- POST .../verify-drop | .../complete → Confirm delivery → Delivered
- PATCH .../status CANCELLED → mobile "POD" (cancel delivery/pickup) → Cancelled
"""
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver_payment_collection import DriverPaymentCollection
from app.models.operations import PodRecord
from app.models.order import OrderStatus
from app.modules.fleet.constants import TERMINAL_ORDER_STATUSES
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.schemas.trip_sheet_driver import (
    CashPaymentRequest,
    TripStatusUpdateRequest,
    VerifyDropRequest,
    VerifyPickupRequest,
)
from app.modules.fleet.services.driver_assignment_runtime_service import (
    build_assignment_trip_detail,
    resolve_open_work,
)


async def get_trip_detail(db: AsyncSession, driver: Driver, order_id: str) -> dict:
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    return build_assignment_trip_detail(kind, assignment, order)


async def update_order_status(
    db: AsyncSession, driver: Driver, order_id: str, payload: TripStatusUpdateRequest
) -> dict:
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    new_status = (payload.status or "").strip().upper()

    # Mobile "POD" (and any cancel) → Cancelled. Intermediate statuses are not tracked.
    if new_status in {"CANCELLED", "CANCEL"}:
        if order.status in TERMINAL_ORDER_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order is already in a terminal status",
            )
        reason = (payload.reason or "").strip()
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reason is required when status is CANCELLED",
            )
        phase = (payload.phase or "").strip().upper()
        if phase not in {"PICKUP", "DELIVERY"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="phase must be PICKUP or DELIVERY when status is CANCELLED",
            )
        cancelled_at = payload.timestamp or datetime.utcnow()
        order.previous_status = order.status
        order.status = OrderStatus.CANCELLED.value
        assignment.status = "cancelled"
        assignment.updated_at = cancelled_at
        meta = dict(order.meta or {})
        meta["cancellation"] = {
            "reason": reason,
            "phase": phase,
            "timestamp": cancelled_at.isoformat(),
            "location": payload.location,
            "driverId": driver.id,
            "assignmentId": assignment.id,
            "assignmentKind": kind,
        }
        order.meta = meta
        await db.flush()
        return {
            "tripId": order.id,
            "tripSheetId": assignment.id,
            "status": "CANCELLED",
            "reason": reason,
            "updatedAt": cancelled_at.isoformat(),
            "message": "Trip status updated to CANCELLED successfully.",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported status. Use CANCELLED only (confirm pickup/delivery via verify endpoints).",
    )


async def verify_pickup(
    db: AsyncSession, driver: Driver, order_id: str, payload: VerifyPickupRequest
) -> dict:
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    if kind != "pickup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has a delivery assignment, not a pickup assignment",
        )

    assignment.status = "completed"
    assignment.updated_at = datetime.utcnow()
    order.previous_status = order.status
    order.status = OrderStatus.PICKED.value
    await db.flush()
    return {
        "tripId": order.id,
        "tripSheetId": assignment.id,
        "status": "PICKUP_COMPLETED",
        "nextStep": "IN_TRANSIT",
        "message": "Pickup confirmed.",
        "orderStatus": order.status,
    }


async def verify_drop(
    db: AsyncSession, driver: Driver, order_id: str, payload: VerifyDropRequest
) -> dict:
    """Confirm delivery (mobile success path). Not the mobile 'POD' cancel action."""
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    if kind != "delivery":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has a pickup assignment, not a delivery assignment",
        )

    receiver = payload.receiverName or (order.consignee.name if order.consignee else "Receiver")
    existing = await db.execute(select(PodRecord).where(PodRecord.order_id == order.id))
    pod = existing.scalar_one_or_none()
    if pod:
        pod.receiver_name = receiver
        pod.received_at = payload.confirmedAt or datetime.utcnow()
        pod.signature_url = payload.signatureUrl
        pod.otp_verified = False
    else:
        db.add(
            PodRecord(
                id=str(uuid.uuid4()),
                order_id=order.id,
                receiver_name=receiver,
                received_at=payload.confirmedAt or datetime.utcnow(),
                delivery_staff_id=driver.user_id,
                otp_verified=False,
                signature_url=payload.signatureUrl,
            )
        )

    assignment.status = "completed"
    assignment.updated_at = datetime.utcnow()
    order.previous_status = order.status
    order.status = OrderStatus.DELIVERED.value
    await db.flush()

    amount = float(order.cod_amount or order.to_pay_amount or order.total_freight or 0)
    return {
        "tripId": order.id,
        "tripSheetId": assignment.id,
        "status": "DELIVERY_COMPLETED",
        "paymentRequired": False,
        "paymentStatus": "PAID" if (order.payment_method or "").lower() == "prepaid" else "PENDING",
        "amount": amount,
        "paymentMethod": order.payment_method,
        "upiId": None,
        "paymentReference": None,
        "message": "Delivery confirmed.",
        "orderStatus": order.status,
    }


async def complete_trip(db: AsyncSession, driver: Driver, order_id: str) -> dict:
    """Same success path as verify-drop when the app calls /complete."""
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    if kind != "delivery":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete is only for delivery assignments",
        )
    if order.status in TERMINAL_ORDER_STATUSES and order.status != OrderStatus.DELIVERED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order cannot be completed")
    assignment.status = "completed"
    assignment.updated_at = datetime.utcnow()
    order.previous_status = order.status
    order.status = OrderStatus.DELIVERED.value
    await db.flush()
    return {"success": True, "message": "Trip completed successfully"}


async def get_payment_info(db: AsyncSession, driver: Driver, order_id: str) -> dict:
    kind, assignment, order = await resolve_open_work(db, driver, order_id)
    amount = float(order.cod_amount or order.to_pay_amount or order.total_freight or 0)
    paid = (order.payment_method or "").lower() == "prepaid" or order.status == OrderStatus.DELIVERED.value
    return {
        "tripId": order.id,
        "tripSheetId": assignment.id,
        "orderId": order.order_number,
        "customerName": order.consignee.name if order.consignee else "",
        "amount": amount,
        "currency": "INR",
        "paymentStatus": "PAID" if paid else "PENDING",
        "paymentMethod": order.payment_method,
        "upiId": "roadoz@ybl",
        "merchantName": "Roadoz Courier Pvt Ltd",
        "paymentReference": f"PAY-{order.order_number}",
        "assignmentKind": kind,
    }


async def submit_cash_payment(db: AsyncSession, driver: Driver, payload: CashPaymentRequest) -> dict:
    _kind, assignment, order = await resolve_open_work(db, driver, payload.orderId)
    ref = f"PAY-{order.order_number}"
    existing = await db.execute(
        select(DriverPaymentCollection).where(DriverPaymentCollection.payment_reference == ref)
    )
    record = existing.scalar_one_or_none()
    if not record:
        record = DriverPaymentCollection(
            id=str(uuid.uuid4()),
            order_id=order.id,
            driver_id=driver.id,
            trip_sheet_id=None,
            amount=payload.amount,
            payment_method="Cash",
            payment_reference=ref,
            status="SUCCESS",
            paid_at=payload.collectedAt or datetime.utcnow(),
        )
        db.add(record)
    else:
        record.status = "SUCCESS"
        record.paid_at = payload.collectedAt or datetime.utcnow()
    assignment.status = "completed"
    assignment.updated_at = datetime.utcnow()
    order.previous_status = order.status
    order.status = OrderStatus.DELIVERED.value
    await db.flush()
    return {"success": True, "message": "Cash collected successfully"}


async def get_payment_status(db: AsyncSession, payment_reference: str) -> dict:
    result = await db.execute(
        select(DriverPaymentCollection).where(DriverPaymentCollection.payment_reference == payment_reference)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {
            "status": "PENDING",
            "paymentReference": payment_reference,
            "amount": 0,
            "transactionId": None,
            "paidAt": None,
            "paymentMethod": "UPI",
        }
    return {
        "status": record.status,
        "paymentReference": record.payment_reference,
        "amount": float(record.amount),
        "transactionId": record.transaction_id,
        "paidAt": record.paid_at.isoformat() if record.paid_at else None,
        "paymentMethod": record.payment_method,
    }
