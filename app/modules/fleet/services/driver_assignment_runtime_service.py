"""Mobile driver work via PickupAssignment / DeliveryAssignment.

Existing /api/v1/driver/trips/* URLs stay; tripSheetId is the assignment id.
Mobile labels: Confirm delivery = success; POD = cancel delivery (PATCH CANCELLED).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.delivery_assignment import DeliveryAssignment
from app.models.order import Order
from app.models.pickup_assignment import PickupAssignment
from app.modules.fleet.constants import TERMINAL_ORDER_STATUSES
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.schemas.trip_sheet_driver import (
    MoneyOut,
    SheetSummaryOut,
    TripListItemOut,
    TripRespondRequest,
)
from app.modules.fleet.services.trip_sheet_flatten_mapper import (
    _location_from_consignee,
    _location_from_pickup,
    _progress_label,
)

AssignmentKind = Literal["pickup", "delivery"]
OPEN_STATUSES = ("assigned", "in_progress")


def _card_status(*, assignment_status: str, order: Order, for_new: bool) -> str:
    if for_new or assignment_status == "assigned":
        return "NEW"
    order_status = (order.status or "").strip()
    if order_status.lower() in {s.lower() for s in TERMINAL_ORDER_STATUSES}:
        return "COMPLETED"
    if order_status in {"Picked", "PICKED"}:
        return "READY_FOR_PICKUP"
    if order_status in {"In_transit", "IN_TRANSIT", "In Transit"}:
        return "IN_TRANSIT"
    if order_status in {"Ofd", "OFD", "Out_for_delivery", "Out for delivery"}:
        return "NEXT"
    return "NEXT"


def assignment_to_list_item(
    kind: AssignmentKind,
    assignment: PickupAssignment | DeliveryAssignment,
    order: Order,
    *,
    for_new: bool,
) -> TripListItemOut:
    consignee = order.consignee
    pickup = order.pickup_address
    card_status = _card_status(assignment_status=assignment.status, order=order, for_new=for_new)
    payment_type = (order.payment_method or "Prepaid").upper().replace(" ", "_")
    trip_type = "PICKUP" if kind == "pickup" else "DELIVERY"
    return TripListItemOut(
        id=order.id,
        tripSheetId=assignment.id,
        deliveryId=order.order_number,
        orderId=order.id,
        customerName=consignee.name if consignee else "Customer",
        status=card_status,
        tripType=trip_type,
        isExpress=(order.service_type or "").lower() == "express",
        assignedTime=assignment.created_at,
        pickupLocation=_location_from_pickup(pickup),
        dropLocation=_location_from_consignee(consignee),
        earnings=MoneyOut(amount=float(order.total_freight or 0), currency="INR"),
        package={"type": order.order_type, "weight": f"{float(order.total_weight_kg or 0)} kg"},
        payment={"type": payment_type, "amount": float(order.cod_amount or order.total_freight or 0)},
        progress=_progress_label(card_status),
        sheetSummary=SheetSummaryOut(totalPackages=1, destinationCity=getattr(consignee, "city", None)),
        isAccepted=assignment.status == "in_progress" or assignment.status == "completed",
    )


async def list_new_assignment_trips(db: AsyncSession, driver: Driver) -> list[TripListItemOut]:
    if not driver.online or driver.onboarding_status != "approved":
        return []
    pickups = (
        await db.execute(
            select(PickupAssignment)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
            )
            .where(
                PickupAssignment.driver_id == driver.id,
                PickupAssignment.status == "assigned",
            )
            .order_by(PickupAssignment.created_at.desc())
        )
    ).scalars().all()
    deliveries = (
        await db.execute(
            select(DeliveryAssignment)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
            )
            .where(
                DeliveryAssignment.driver_id == driver.id,
                DeliveryAssignment.status == "assigned",
            )
            .order_by(DeliveryAssignment.created_at.desc())
        )
    ).scalars().all()
    items: list[TripListItemOut] = []
    for a in pickups:
        if a.order:
            items.append(assignment_to_list_item("pickup", a, a.order, for_new=True))
    for a in deliveries:
        if a.order:
            items.append(assignment_to_list_item("delivery", a, a.order, for_new=True))
    return items


async def list_active_assignment_trips(db: AsyncSession, driver: Driver) -> list[TripListItemOut]:
    pickups = (
        await db.execute(
            select(PickupAssignment)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
            )
            .where(
                PickupAssignment.driver_id == driver.id,
                PickupAssignment.status == "in_progress",
            )
            .order_by(PickupAssignment.created_at.desc())
        )
    ).scalars().all()
    deliveries = (
        await db.execute(
            select(DeliveryAssignment)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
            )
            .where(
                DeliveryAssignment.driver_id == driver.id,
                DeliveryAssignment.status == "in_progress",
            )
            .order_by(DeliveryAssignment.created_at.desc())
        )
    ).scalars().all()
    items: list[TripListItemOut] = []
    for a in pickups:
        if a.order and (a.order.status or "") not in TERMINAL_ORDER_STATUSES:
            items.append(assignment_to_list_item("pickup", a, a.order, for_new=False))
    for a in deliveries:
        if a.order and (a.order.status or "") not in TERMINAL_ORDER_STATUSES:
            items.append(assignment_to_list_item("delivery", a, a.order, for_new=False))
    return items


async def resolve_open_work(
    db: AsyncSession, driver: Driver, order_id: str
) -> tuple[AssignmentKind, PickupAssignment | DeliveryAssignment, Order]:
    pickup = (
        await db.execute(
            select(PickupAssignment)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
                selectinload(PickupAssignment.order).selectinload(Order.packages),
                selectinload(PickupAssignment.order).selectinload(Order.items),
            )
            .where(
                PickupAssignment.driver_id == driver.id,
                PickupAssignment.order_id == order_id,
                PickupAssignment.status.in_(OPEN_STATUSES),
            )
            .order_by(PickupAssignment.created_at.desc())
        )
    ).scalars().first()
    if pickup and pickup.order:
        return "pickup", pickup, pickup.order

    delivery = (
        await db.execute(
            select(DeliveryAssignment)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
                selectinload(DeliveryAssignment.order).selectinload(Order.packages),
                selectinload(DeliveryAssignment.order).selectinload(Order.items),
                selectinload(DeliveryAssignment.consignee),
            )
            .where(
                DeliveryAssignment.driver_id == driver.id,
                DeliveryAssignment.order_id == order_id,
                DeliveryAssignment.status.in_(OPEN_STATUSES),
            )
            .order_by(DeliveryAssignment.created_at.desc())
        )
    ).scalars().first()
    if delivery and delivery.order:
        return "delivery", delivery, delivery.order

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No open pickup or delivery assignment for this order",
    )


async def resolve_assignment_by_id(
    db: AsyncSession, driver: Driver, assignment_id: str
) -> tuple[AssignmentKind, PickupAssignment | DeliveryAssignment]:
    pickup = (
        await db.execute(
            select(PickupAssignment).where(
                PickupAssignment.id == assignment_id,
                PickupAssignment.driver_id == driver.id,
            )
        )
    ).scalar_one_or_none()
    if pickup:
        return "pickup", pickup
    delivery = (
        await db.execute(
            select(DeliveryAssignment).where(
                DeliveryAssignment.id == assignment_id,
                DeliveryAssignment.driver_id == driver.id,
            )
        )
    ).scalar_one_or_none()
    if delivery:
        return "delivery", delivery
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")


async def respond_to_assignment(
    db: AsyncSession, driver: Driver, assignment_id: str, payload: TripRespondRequest
) -> dict:
    kind, assignment = await resolve_assignment_by_id(db, driver, assignment_id)
    if assignment.status != "assigned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assignment is not pending acceptance",
        )
    action = payload.action.upper()
    if action == "ACCEPT":
        assignment.status = "in_progress"
        assignment.updated_at = datetime.utcnow()
        await db.flush()
        return {
            "tripSheetId": assignment.id,
            "status": "ACCEPTED",
            "nextStep": "ARRIVED_AT_PICKUP" if kind == "pickup" else "ARRIVED_AT_DROP",
            "assignmentKind": kind,
        }
    if action == "DECLINE":
        # Decline assignment only — do not cancel the order.
        assignment.status = "cancelled"
        assignment.updated_at = datetime.utcnow()
        await db.flush()
        return {"tripSheetId": assignment.id, "status": "DECLINED", "assignmentKind": kind}
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid action")


def build_assignment_trip_detail(
    kind: AssignmentKind,
    assignment: PickupAssignment | DeliveryAssignment,
    order: Order,
) -> dict:
    pickup = order.pickup_address
    consignee = order.consignee
    amount = float(order.cod_amount or order.to_pay_amount or order.total_freight or 0)
    payment_status = "PAID" if (order.payment_method or "").lower() == "prepaid" else "PENDING"

    def stop(stop_type: str, title: str, location, customer_name, phone, role):
        if not location and stop_type == "PICKUP":
            return None
        loc = location
        address = ", ".join(
            p
            for p in [
                getattr(loc, "address_line_1", None),
                getattr(loc, "address_line_2", None),
                getattr(loc, "city", None),
                getattr(loc, "pincode", None),
            ]
            if p
        )
        return {
            "id": f"stop-{stop_type.lower()}-{order.id}",
            "type": stop_type,
            "title": title,
            "location": {
                "name": getattr(loc, "nickname", None) or getattr(loc, "name", None) or title,
                "address": address,
                "latitude": float(getattr(loc, "latitude", 0) or 0) if getattr(loc, "latitude", None) else None,
                "longitude": float(getattr(loc, "longitude", 0) or 0) if getattr(loc, "longitude", None) else None,
                "contactPhone": phone,
            },
            "customer": {
                "name": customer_name or "Contact",
                "role": role,
                "phone": phone,
                "avatarInitials": "".join(w[0] for w in (customer_name or "NA").split()[:2]).upper(),
            },
        }

    packages = [
        {
            "id": pkg.id,
            "packageIndex": pkg.package_index,
            "count": pkg.count,
            "weightUnit": pkg.weight_unit,
            "lengthCm": float(pkg.length_cm or 0),
            "breadthCm": float(pkg.breadth_cm or 0),
            "heightCm": float(pkg.height_cm or 0),
            "volWeightKg": float(pkg.vol_weight_kg or 0),
            "physicalWeightKg": float(pkg.physical_weight_kg or 0),
        }
        for pkg in (order.packages or [])
    ]
    items = [
        {
            "id": item.id,
            "productName": item.product_name,
            "sku": item.sku,
            "unitPrice": float(item.unit_price or 0),
            "qty": item.qty,
            "total": float(item.total or 0),
            "packageIndex": item.package_index,
        }
        for item in (order.items or [])
    ]

    return {
        "id": order.id,
        "tripSheetId": assignment.id,
        "orderId": order.order_number,
        "isUrgent": (order.service_type or "").lower() == "express",
        "tripType": "PICKUP" if kind == "pickup" else "DELIVERY",
        "status": order.status,
        "assignmentStatus": assignment.status,
        "paymentStatus": payment_status,
        "amount": amount,
        "packageSummary": {
            "type": order.order_type,
            "totalWeightKg": float(order.total_weight_kg or 0),
            "totalPackages": len(packages),
            "totalItems": len(items),
        },
        "packages": packages,
        "items": items,
        "pickupStop": stop(
            "PICKUP",
            "PICKUP LOCATION",
            pickup,
            pickup.contact_name if pickup else None,
            pickup.phone if pickup else None,
            "Sender",
        ),
        "deliveryStop": stop(
            "DELIVERY",
            "DELIVERY LOCATION",
            consignee,
            consignee.name if consignee else None,
            consignee.mobile if consignee else None,
            "Receiver",
        ),
    }


async def list_assignment_order_history(
    db: AsyncSession, driver: Driver, page: int, limit: int
) -> dict:
    offset = (page - 1) * limit
    pickups = (
        await db.execute(
            select(Order)
            .join(PickupAssignment, PickupAssignment.order_id == Order.id)
            .options(selectinload(Order.pickup_address), selectinload(Order.consignee))
            .where(
                PickupAssignment.driver_id == driver.id,
                or_(
                    PickupAssignment.status == "completed",
                    PickupAssignment.status == "cancelled",
                ),
                Order.status.in_(list(TERMINAL_ORDER_STATUSES)),
            )
        )
    ).scalars().all()
    deliveries = (
        await db.execute(
            select(Order)
            .join(DeliveryAssignment, DeliveryAssignment.order_id == Order.id)
            .options(selectinload(Order.pickup_address), selectinload(Order.consignee))
            .where(
                DeliveryAssignment.driver_id == driver.id,
                or_(
                    DeliveryAssignment.status == "completed",
                    DeliveryAssignment.status == "cancelled",
                ),
                Order.status.in_(list(TERMINAL_ORDER_STATUSES)),
            )
        )
    ).scalars().all()
    by_id: dict[str, Order] = {}
    for o in [*pickups, *deliveries]:
        by_id[o.id] = o
    orders_sorted = sorted(by_id.values(), key=lambda o: o.updated_at or datetime.min, reverse=True)
    total = len(orders_sorted)
    page_orders = orders_sorted[offset : offset + limit]
    return {
        "orders": [
            {
                "id": order.order_number,
                "sender": order.pickup_address.nickname if order.pickup_address else "",
                "recipient": order.consignee.name if order.consignee else "",
                "status": order.status,
                "weight": f"{float(order.total_weight_kg or 0)} kg",
            }
            for order in page_orders
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


async def export_assignment_order_history(
    db: AsyncSession,
    driver: Driver,
    *,
    start_dt: datetime | None,
    end_dt: datetime | None,
    row_cap: int,
    order_to_row,
) -> list[dict[str, Any]]:
    filters_common = [Order.status.in_(list(TERMINAL_ORDER_STATUSES))]
    if start_dt is not None and end_dt is not None:
        filters_common.append(Order.updated_at >= start_dt)
        filters_common.append(Order.updated_at <= end_dt)

    pickups = (
        await db.execute(
            select(Order)
            .join(PickupAssignment, PickupAssignment.order_id == Order.id)
            .options(selectinload(Order.pickup_address), selectinload(Order.consignee))
            .where(
                PickupAssignment.driver_id == driver.id,
                PickupAssignment.status.in_(("completed", "cancelled")),
                *filters_common,
            )
            .order_by(Order.updated_at.desc())
            .limit(row_cap)
        )
    ).scalars().all()
    deliveries = (
        await db.execute(
            select(Order)
            .join(DeliveryAssignment, DeliveryAssignment.order_id == Order.id)
            .options(selectinload(Order.pickup_address), selectinload(Order.consignee))
            .where(
                DeliveryAssignment.driver_id == driver.id,
                DeliveryAssignment.status.in_(("completed", "cancelled")),
                *filters_common,
            )
            .order_by(Order.updated_at.desc())
            .limit(row_cap)
        )
    ).scalars().all()
    by_id: dict[str, Order] = {}
    for o in [*pickups, *deliveries]:
        by_id[o.id] = o
    orders_sorted = sorted(by_id.values(), key=lambda o: o.updated_at or datetime.min, reverse=True)[
        :row_cap
    ]
    return [order_to_row(o) for o in orders_sorted]
