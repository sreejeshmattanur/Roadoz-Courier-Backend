import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.order import OrderItem, OrderPackage, BagOrder
from app.models.warehouse import OrderWarehouseAddress
from app.models.franchise import OrderFranchiseAddress
from app.services.order_service import _build_order_out
from app.schemas.order import ConsigneeOut
from app.schemas.delivery_assignment import DriverBrief, VehicleBrief


from app.core.config import settings
from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.consignee import Consignee
from app.models.delivery_assignment import DeliveryAssignment
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.models.vehicle import Vehicle
from app.services.order_service import _resolve_franchise_id, _resolve_warehouse_id
from app.schemas.delivery_assignment import (
    DeliveryAssignmentCreate,
    DeliveryAssignmentListResponse,
    DeliveryAssignmentOut,
    VerifyOTPRequest,
)
from app.utils.smtp import send_assignment_otp_email

router = APIRouter(prefix="/delivery-assignments", tags=["Delivery Assignment"])



def _map_delivery_assignment_out(a: DeliveryAssignment) -> DeliveryAssignmentOut:
    return DeliveryAssignmentOut(
        id=a.id,
        order_id=a.order_id,
        consignee_id=a.consignee_id,
        franchise_id=a.franchise_id,
        warehouse_id=a.warehouse_id,
        driver_id=a.driver_id,
        vehicle_id=a.vehicle_id,
        delivery_address=a.delivery_address,
        otp_status=a.otp_status,
        status=a.status,
        created_by=a.created_by,
        created_at=a.created_at,
        updated_at=a.updated_at,
        driver=DriverBrief.model_validate(a.driver) if a.driver else None,
        vehicle=VehicleBrief.model_validate(a.vehicle) if a.vehicle else None,
        consignee=ConsigneeOut.model_validate(a.consignee) if a.consignee else None,
        order=_build_order_out(a.order) if a.order else None
    )


def _generate_otp(length: int = 6) -> str:
    """Generate a random numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/create", response_model=list[DeliveryAssignmentOut], status_code=status.HTTP_201_CREATED)
async def create_delivery_assignment(
    payload: DeliveryAssignmentCreate,
    current_user: User = Depends(require_permission("delivery_assignment:create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create Delivery Assignments for a list of order barcodes.

    Rules:
    - The franchise creating this assignment must be the destination_franchise_id
      of the trip sheet that carried these orders (i.e. the receiving franchise).
    - Driver and vehicle must belong to that same destination franchise.
    - Order must be IN_TRANSIT status (arrived at destination franchise).
    - On creation: order status is promoted to OUT_FOR_DELIVERY.
    - Prevents duplicate active delivery assignments per order.
    """
    from app.models.trip_sheet import TripSheet, TripSheetOrder

    # Resolve the calling user's franchise
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    # Validate driver belongs to the destination franchise
    driver = (await db.execute(select(Driver).where(Driver.id == payload.driver_id))).scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    if franchise_id and driver.franchise_id != franchise_id:
        raise HTTPException(
            status_code=403,
            detail=f"Driver {payload.driver_id} does not belong to your franchise."
        )

    # Validate vehicle belongs to the destination franchise
    vehicle = (await db.execute(select(Vehicle).where(Vehicle.id == payload.vehicle_id))).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if franchise_id and vehicle.franchise_id != franchise_id:
        raise HTTPException(
            status_code=403,
            detail=f"Vehicle {payload.vehicle_id} does not belong to your franchise."
        )

    created_assignments = []

    for barcode in payload.order_barcodes:
        # Fetch the order by barcode
        order = (await db.execute(select(Order).where(Order.order_number == barcode))).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail=f"Order not found for barcode: {barcode}")

        # Verify this franchise is the destination franchise for this order's trip sheet
        if franchise_id:
            trip_sheet_order = (
                await db.execute(
                    select(TripSheetOrder).where(TripSheetOrder.order_id == order.id)
                )
            ).scalar_one_or_none()

            if not trip_sheet_order:
                raise HTTPException(
                    status_code=403,
                    detail=f"Order {barcode} has not been dispatched via a trip sheet."
                )

            trip_sheet = (
                await db.execute(
                    select(TripSheet).where(
                        TripSheet.id == trip_sheet_order.trip_sheet_id,
                        TripSheet.destination_franchise_id == franchise_id,
                    )
                )
            ).scalar_one_or_none()

            if not trip_sheet:
                raise HTTPException(
                    status_code=403,
                    detail=f"Order {barcode} was not dispatched to your franchise. You cannot create a delivery assignment for it."
                )


        # Prevent duplicate active delivery assignment
        existing = (
            await db.execute(
                select(DeliveryAssignment).where(
                    DeliveryAssignment.order_id == order.id,
                    DeliveryAssignment.status != "cancelled",
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A delivery assignment already exists for order {barcode} (id: {existing.id}). Cancel it first.",
            )

        # Fetch consignee
        consignee = (
            await db.execute(select(Consignee).where(Consignee.id == order.consignee_id))
        ).scalar_one_or_none()
        if not consignee:
            raise HTTPException(status_code=404, detail=f"Consignee not found for order {barcode}")

        # Build delivery address snapshot
        delivery_address = (
            f"{consignee.address_line_1}"
            + (f", {consignee.address_line_2}" if consignee.address_line_2 else "")
            + f", {consignee.city}, {consignee.state} – {consignee.pincode}"
        )

        # Generate OTP
        otp = _generate_otp()
        otp_expiry = datetime.utcnow() + timedelta(minutes=settings.OTP__MINUTES)

        # Promote order to Ofd (out for delivery)
        order.previous_status = order.status
        order.status = OrderStatus.OFD.value

        # Persist the assignment
        assignment = DeliveryAssignment(
            order_id=order.id,
            consignee_id=consignee.id,
            driver_id=payload.driver_id,
            vehicle_id=payload.vehicle_id,
            franchise_id=franchise_id,
            warehouse_id=warehouse_id,
            delivery_address=delivery_address,
            otp=otp,
            otp_expiry=otp_expiry,
            otp_status="pending",
            status="assigned",
            created_by=current_user.id,
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
        created_assignments.append(assignment)

        # Send OTP to consignee email
        if consignee.email:
            await send_assignment_otp_email(
                to_email=consignee.email,
                customer_name=consignee.name or "Customer",
                order_number=order.order_number,
                assignment_type="Delivery",
                otp=otp,
            )

    return [_map_delivery_assignment_out(a) for a in created_assignments]


# ─────────────────────────────────────────────────────────────────────────────
# LIST
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/list", response_model=DeliveryAssignmentListResponse)
async def list_delivery_assignments(
    order_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(require_permission("delivery_assignment:view")),
    db: AsyncSession = Depends(get_db),
):
    """List all delivery assignments scoped to the current user's franchise/warehouse."""
    query = select(DeliveryAssignment)

    # Role-based scoping
    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id:
        query = query.where(DeliveryAssignment.franchise_id == franchise_id)

    warehouse_id = await _resolve_warehouse_id(db, current_user)
    if warehouse_id:
        query = query.where(DeliveryAssignment.warehouse_id == warehouse_id)

    if order_id:
        query = query.where(DeliveryAssignment.order_id == order_id)
    if status_filter:
        query = query.where(DeliveryAssignment.status == status_filter)

    
    query = query.options(
        selectinload(DeliveryAssignment.order).selectinload(Order.items),
        selectinload(DeliveryAssignment.order).selectinload(Order.packages),
        selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
        selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
        selectinload(DeliveryAssignment.order).selectinload(Order.creator),
        selectinload(DeliveryAssignment.order).selectinload(Order.franchise),
        selectinload(DeliveryAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
        selectinload(DeliveryAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
        selectinload(DeliveryAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
        selectinload(DeliveryAssignment.order).selectinload(Order.bulk_order),
        selectinload(DeliveryAssignment.consignee),
        selectinload(DeliveryAssignment.driver),
        selectinload(DeliveryAssignment.vehicle)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    return DeliveryAssignmentListResponse(
        total=len(items),
        items=[_map_delivery_assignment_out(a) for a in items],
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET ONE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{assignment_id}/onebyone", response_model=DeliveryAssignmentOut)
async def get_delivery_assignment(
    assignment_id: str,
    current_user: User = Depends(require_permission("delivery_assignment:view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific delivery assignment by ID."""
    assignment = (
        await db.execute(
            select(DeliveryAssignment)
            .where(DeliveryAssignment.id == assignment_id)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.items),
                selectinload(DeliveryAssignment.order).selectinload(Order.packages),
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
                selectinload(DeliveryAssignment.order).selectinload(Order.creator),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise),
                selectinload(DeliveryAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(DeliveryAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.bulk_order),
                selectinload(DeliveryAssignment.consignee),
                selectinload(DeliveryAssignment.driver),
                selectinload(DeliveryAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Delivery assignment not found")
    return _map_delivery_assignment_out(assignment)


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY OTP
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{assignment_id}/verify-otp")
async def verify_delivery_otp(
    assignment_id: str,
    body: VerifyOTPRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the OTP for a delivery assignment.
    On success: otp_status → verified, status → completed, order → Delivered.
    """
    assignment = (
        await db.execute(
            select(DeliveryAssignment)
            .where(DeliveryAssignment.id == assignment_id)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.items),
                selectinload(DeliveryAssignment.order).selectinload(Order.packages),
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
                selectinload(DeliveryAssignment.order).selectinload(Order.creator),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise),
                selectinload(DeliveryAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(DeliveryAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.bulk_order),
                selectinload(DeliveryAssignment.consignee),
                selectinload(DeliveryAssignment.driver),
                selectinload(DeliveryAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Delivery assignment not found")

    if assignment.otp_status == "verified":
        raise HTTPException(status_code=400, detail="OTP has already been verified")

    if assignment.status == "cancelled":
        raise HTTPException(status_code=400, detail="Assignment has been cancelled")

    if assignment.otp_expiry and datetime.utcnow() > assignment.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new assignment.")

    if assignment.otp != body.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    assignment.otp_status = "verified"
    assignment.status = "completed"
    assignment.updated_at = datetime.utcnow()

    # Promote order to Delivered
    order = (await db.execute(select(Order).where(Order.id == assignment.order_id))).scalar_one_or_none()
    if order:
        order.previous_status = order.status
        order.status = OrderStatus.DELIVERED.value

    await db.commit()

    return {"message": "OTP verified successfully. Delivery marked as completed.", "assignment_id": assignment_id}


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/{assignment_id}/cancel")
async def cancel_delivery_assignment(
    assignment_id: str,
    current_user: User = Depends(require_permission("delivery_assignment:create")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an active delivery assignment."""
    assignment = (
        await db.execute(
            select(DeliveryAssignment)
            .where(DeliveryAssignment.id == assignment_id)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.items),
                selectinload(DeliveryAssignment.order).selectinload(Order.packages),
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
                selectinload(DeliveryAssignment.order).selectinload(Order.creator),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise),
                selectinload(DeliveryAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(DeliveryAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.bulk_order),
                selectinload(DeliveryAssignment.consignee),
                selectinload(DeliveryAssignment.driver),
                selectinload(DeliveryAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Delivery assignment not found")

    if assignment.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a {assignment.status} assignment")

    assignment.status = "cancelled"
    assignment.updated_at = datetime.utcnow()

    # Revert order back to In_transit when still OFD / Out_for_delivery
    order = (await db.execute(select(Order).where(Order.id == assignment.order_id))).scalar_one_or_none()
    if order and order.status in {OrderStatus.OFD.value, OrderStatus.OUT_FOR_DELIVERY.value}:
        order.status = OrderStatus.IN_TRANSIT.value

    await db.commit()

    return {"message": "Delivery assignment cancelled successfully", "assignment_id": assignment_id}


# ─────────────────────────────────────────────────────────────────────────────
# RESEND OTP
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{assignment_id}/resend-otp")
async def resend_delivery_otp(
    assignment_id: str,
    current_user: User = Depends(require_permission("delivery_assignment:create")),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate and resend OTP for a delivery assignment."""
    assignment = (
        await db.execute(
            select(DeliveryAssignment)
            .where(DeliveryAssignment.id == assignment_id)
            .options(
                selectinload(DeliveryAssignment.order).selectinload(Order.items),
                selectinload(DeliveryAssignment.order).selectinload(Order.packages),
                selectinload(DeliveryAssignment.order).selectinload(Order.pickup_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.consignee),
                selectinload(DeliveryAssignment.order).selectinload(Order.creator),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise),
                selectinload(DeliveryAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(DeliveryAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(DeliveryAssignment.order).selectinload(Order.bulk_order),
                selectinload(DeliveryAssignment.consignee),
                selectinload(DeliveryAssignment.driver),
                selectinload(DeliveryAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Delivery assignment not found")

    if assignment.otp_status == "verified":
        raise HTTPException(status_code=400, detail="OTP already verified")
    if assignment.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot resend OTP for a {assignment.status} assignment")

    new_otp = _generate_otp()
    assignment.otp = new_otp
    assignment.otp_expiry = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    assignment.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(assignment)

    order = (await db.execute(select(Order).where(Order.id == assignment.order_id))).scalar_one_or_none()
    consignee = (
        await db.execute(select(Consignee).where(Consignee.id == assignment.consignee_id))
    ).scalar_one_or_none()

    if consignee and consignee.email and order:
        await send_assignment_otp_email(
            to_email=consignee.email,
            customer_name=consignee.name or "Customer",
            order_number=order.order_number,
            assignment_type="Delivery",
            otp=new_otp,
        )

    return {"message": "OTP regenerated and sent successfully"}
