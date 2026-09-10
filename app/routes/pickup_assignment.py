import random
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.order import OrderItem, OrderPackage, BagOrder
from app.models.order import OrderStatus
from app.models.warehouse import OrderWarehouseAddress
from app.models.franchise import OrderFranchiseAddress
from app.services.order_service import _build_order_out
from app.schemas.pickup_assignment import DriverBrief, VehicleBrief


from app.core.config import settings
from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.order import Order
from app.models.pickup_assignment import PickupAssignment
from app.models.user import User
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.models.vehicle import Vehicle
from app.services.order_service import _resolve_franchise_id, _resolve_warehouse_id
from app.schemas.pickup_assignment import (

    PickupAssignmentCreate,
    PickupAssignmentListResponse,
    PickupAssignmentOut,
    VerifyOTPRequest,
)
from app.utils.smtp import send_assignment_otp_email

router = APIRouter(prefix="/pickup-assignments", tags=["Pickup Assignment"])



def _map_pickup_assignment_out(a: PickupAssignment) -> PickupAssignmentOut:
    return PickupAssignmentOut(
        id=a.id,
        order_id=a.order_id,
        franchise_id=a.franchise_id,
        warehouse_id=a.warehouse_id,
        driver_id=a.driver_id,
        vehicle_id=a.vehicle_id,
        otp_status=a.otp_status,
        status=a.status,
        created_by=a.created_by,
        created_at=a.created_at,
        updated_at=a.updated_at,
        driver=DriverBrief.model_validate(a.driver) if a.driver else None,
        vehicle=VehicleBrief.model_validate(a.vehicle) if a.vehicle else None,
        order=_build_order_out(a.order) if a.order else None
    )


def _generate_otp(length: int = 6) -> str:
    """Generate a random numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/create", response_model=list[PickupAssignmentOut], status_code=status.HTTP_201_CREATED)
async def create_pickup_assignment(
    payload: PickupAssignmentCreate,
    current_user: User = Depends(require_permission("pickup_assignment:create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create Pickup Assignments for a list of orders.
    - Validates driver and vehicle exist.
    - Validates each order exists by order_barcode.
    - Ensures each order is managed by the user's scoped role.
    - Uses the order's pickup address and sends an OTP to that address email.
    """
    # 1. Validate driver
    driver = (await db.execute(select(Driver).where(Driver.id == payload.driver_id))).scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # 2. Validate vehicle
    vehicle = (await db.execute(select(Vehicle).where(Vehicle.id == payload.vehicle_id))).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    created_assignments = []

    for barcode in payload.order_barcodes:
        # Validate order exists
        order = (await db.execute(select(Order).where(Order.order_number == barcode))).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail=f"Order not found for barcode: {barcode}")

        # Validate Ownership (RBAC)
        if franchise_id and order.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail=f"Not authorized to assign pickups for order {barcode} (different franchise)")
        if warehouse_id and order.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail=f"Not authorized to assign pickups for order {barcode} (different warehouse)")

        # Get pickup address from the order relationship (for OTP email)
        pickup_address = order.pickup_address

        # Prevent assigning if already Picked (exists in any Picked DB tables)
        from app.models.order import PickupToConsignees, FranchiseToDelivery, WarehouseToDelivery
        is_picked = False
        if (await db.execute(select(PickupToConsignees.id).where(PickupToConsignees.order_id == order.id))).scalar_one_or_none():
            is_picked = True
        elif (await db.execute(select(FranchiseToDelivery.id).where(FranchiseToDelivery.order_id == order.id))).scalar_one_or_none():
            is_picked = True
        elif (await db.execute(select(WarehouseToDelivery.id).where(WarehouseToDelivery.order_id == order.id))).scalar_one_or_none():
            is_picked = True

        if is_picked:
            raise HTTPException(
                status_code=400, 
                detail=f"Order {barcode} has already been picked up and cannot be assigned again."
            )

        # Prevent duplicate assignment
        existing = (
            await db.execute(
                select(PickupAssignment).where(
                    PickupAssignment.order_id == order.id,
                    PickupAssignment.status != "cancelled",
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A pickup assignment already exists for order {barcode} (id: {existing.id}). "
                       "Cancel it first before creating a new one.",
            )

        # Generate OTP
        otp = _generate_otp()
        otp_expiry = datetime.utcnow() + timedelta(minutes=settings.OTP__MINUTES)

        # Persist the assignment
        assignment = PickupAssignment(
            order_id=order.id,
            driver_id=payload.driver_id,
            vehicle_id=payload.vehicle_id,
            franchise_id=franchise_id,
            warehouse_id=warehouse_id,
            otp=otp,
            otp_expiry=otp_expiry,
            otp_status="pending",
            status="assigned",
            created_by=current_user.id,
        )
        db.add(assignment)
        # Update Order Status
        order.status = OrderStatus.PICKUP_ASSIGNED.value
        
        await db.commit()
        await db.refresh(assignment)
        await db.refresh(order)
        created_assignments.append(assignment)

        # Send OTP email
        if pickup_address.email:
            await send_assignment_otp_email(
                to_email=pickup_address.email,
                customer_name=pickup_address.contact_name or "Customer",
                order_number=order.order_number,
                assignment_type="Pickup",
                otp=otp,
            )

    return [_map_pickup_assignment_out(a) for a in created_assignments]



# ─────────────────────────────────────────────────────────────────────────────
# LIST
# ─────────────────────────────────────────────────────────────────────────────

# @router.get("/list", response_model=PickupAssignmentListResponse)
# async def list_pickup_assignments(
#     order_id: Optional[str] = Query(None),
#     status_filter: Optional[str] = Query(None, alias="status"),
#     current_user: User = Depends(require_permission("pickup_assignment:view")),
#     db: AsyncSession = Depends(get_db),
# ):
#     """List all pickup assignments with optional filters."""
#     query = select(PickupAssignment)
    
#     # Role-based scoping
#     franchise_id = await _resolve_franchise_id(db, current_user)
#     if franchise_id:
#         query = query.where(PickupAssignment.franchise_id == franchise_id)
        
#     warehouse_id = await _resolve_warehouse_id(db, current_user)
#     if warehouse_id:
#         query = query.where(PickupAssignment.warehouse_id == warehouse_id)

#     if order_id:
#         query = query.where(PickupAssignment.order_id == order_id)
#     if status_filter:
#         query = query.where(PickupAssignment.status == status_filter)

    
#     query = query.options(
#         selectinload(PickupAssignment.order).selectinload(Order.items),
#         selectinload(PickupAssignment.order).selectinload(Order.packages),
#         selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
#         selectinload(PickupAssignment.order).selectinload(Order.consignee),
#         selectinload(PickupAssignment.order).selectinload(Order.creator),
#         selectinload(PickupAssignment.order).selectinload(Order.franchise),
#         selectinload(PickupAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
#         selectinload(PickupAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
#         selectinload(PickupAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
#         selectinload(PickupAssignment.order).selectinload(Order.bulk_order),
#         selectinload(PickupAssignment.driver),
#         selectinload(PickupAssignment.vehicle)
#     )
#     result = await db.execute(query)
#     items = result.scalars().all()
#     return PickupAssignmentListResponse(
#         total=len(items),
#         items=[_map_pickup_assignment_out(a) for a in items],
#     )


@router.get("/list", response_model=PickupAssignmentListResponse)
async def list_pickup_assignments(
    order_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_permission("pickup_assignment:view")),
    db: AsyncSession = Depends(get_db),
):
    """List all pickup assignments with pagination."""

    query = select(PickupAssignment)

    # Role-based scoping
    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id:
        query = query.where(PickupAssignment.franchise_id == franchise_id)

    warehouse_id = await _resolve_warehouse_id(db, current_user)
    if warehouse_id:
        query = query.where(PickupAssignment.warehouse_id == warehouse_id)

    if order_id:
        query = query.where(PickupAssignment.order_id == order_id)

    if status_filter:
        query = query.where(PickupAssignment.status == status_filter)

    # Total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Pagination
    offset = (page - 1) * limit

    query = (
        query.options(
            selectinload(PickupAssignment.order).selectinload(Order.items),
            selectinload(PickupAssignment.order).selectinload(Order.packages),
            selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
            selectinload(PickupAssignment.order).selectinload(Order.consignee),
            selectinload(PickupAssignment.order).selectinload(Order.creator),
            selectinload(PickupAssignment.order).selectinload(Order.franchise),
            selectinload(PickupAssignment.order)
                .selectinload(Order.bag_orders)
                .selectinload(BagOrder.bag),
            selectinload(PickupAssignment.order)
                .selectinload(Order.warehouse_addresses)
                .selectinload(OrderWarehouseAddress.warehouse_address),
            selectinload(PickupAssignment.order)
                .selectinload(Order.franchise_addresses)
                .selectinload(OrderFranchiseAddress.franchise_address),
            selectinload(PickupAssignment.order).selectinload(Order.bulk_order),
            selectinload(PickupAssignment.driver),
            selectinload(PickupAssignment.vehicle),
        )
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    return PickupAssignmentListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit,
        items=[_map_pickup_assignment_out(a) for a in items],
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET ONE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{assignment_id}/onebyone", response_model=PickupAssignmentOut)
async def get_pickup_assignment(
    assignment_id: str,
    current_user: User = Depends(require_permission("pickup_assignment:view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific pickup assignment by ID."""
    assignment = (
        await db.execute(
            select(PickupAssignment)
            .where(PickupAssignment.id == assignment_id)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.items),
                selectinload(PickupAssignment.order).selectinload(Order.packages),
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
                selectinload(PickupAssignment.order).selectinload(Order.creator),
                selectinload(PickupAssignment.order).selectinload(Order.franchise),
                selectinload(PickupAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(PickupAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(PickupAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(PickupAssignment.order).selectinload(Order.bulk_order),
                selectinload(PickupAssignment.driver),
                selectinload(PickupAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Pickup assignment not found")
    return _map_pickup_assignment_out(assignment)


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY OTP
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{assignment_id}/verify-otp")
async def verify_pickup_otp(
    assignment_id: str,
    body: VerifyOTPRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the OTP for a pickup assignment.
    On success: otp_status → verified, status → completed.
    """
    assignment = (
        await db.execute(
            select(PickupAssignment)
            .where(PickupAssignment.id == assignment_id)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.items),
                selectinload(PickupAssignment.order).selectinload(Order.packages),
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
                selectinload(PickupAssignment.order).selectinload(Order.creator),
                selectinload(PickupAssignment.order).selectinload(Order.franchise),
                selectinload(PickupAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(PickupAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(PickupAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(PickupAssignment.order).selectinload(Order.bulk_order),
                selectinload(PickupAssignment.driver),
                selectinload(PickupAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Pickup assignment not found")

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

    order = assignment.order
    if order is None:
        order = (await db.execute(select(Order).where(Order.id == assignment.order_id))).scalar_one_or_none()
    if order:
        order.previous_status = order.status
        order.status = OrderStatus.PICKED.value

    await db.commit()

    return {
        "message": "OTP verified successfully. Pickup marked as completed.",
        "assignment_id": assignment_id,
        "orderStatus": order.status if order else None,
    }



# ─────────────────────────────────────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{assignment_id}/delete")
async def delete_pickup_assignment(
    assignment_id: str,
    current_user: User = Depends(require_permission("pickup_assignment:create")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a pickup assignment completely from the database."""
    assignment = (
        await db.execute(
            select(PickupAssignment)
            .where(PickupAssignment.id == assignment_id)
            .options(
                selectinload(PickupAssignment.order).selectinload(Order.items),
                selectinload(PickupAssignment.order).selectinload(Order.packages),
                selectinload(PickupAssignment.order).selectinload(Order.pickup_address),
                selectinload(PickupAssignment.order).selectinload(Order.consignee),
                selectinload(PickupAssignment.order).selectinload(Order.creator),
                selectinload(PickupAssignment.order).selectinload(Order.franchise),
                selectinload(PickupAssignment.order).selectinload(Order.bag_orders).selectinload(BagOrder.bag),
                selectinload(PickupAssignment.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
                selectinload(PickupAssignment.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
                selectinload(PickupAssignment.order).selectinload(Order.bulk_order),
                selectinload(PickupAssignment.driver),
                selectinload(PickupAssignment.vehicle)
            )
        )
    ).scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Pickup assignment not found")

    await db.delete(assignment)
    await db.commit()

    return {"message": "Pickup assignment deleted successfully", "assignment_id": assignment_id}

