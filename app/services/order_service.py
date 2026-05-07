import math
import uuid
import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.franchise import Franchise
from app.models.pickup_address import PickupAddress
from app.models.consignee import Consignee
from app.models.warehouse import WareHouseAddress
from app.models.order import Order, OrderItem, OrderPackage, OrderStatus
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.wallet_service import debit_for_order
from app.utils.barcode import generate_barcode_base64
from app.schemas.order import (
    PickupAddressCreate,
    PickupAddressUpdate,
    PickupAddressOut,
    PickupAddressListResponse,
    ConsigneeCreate,
    ConsigneeOut,
    ConsigneeListResponse,
    ConsigneeUpdate,
    ConsigneeStatusUpdate,
    OrderCreate,
    OrderOut,
    OrderItemOut,
    OrderPackageOut,
    OrderListResponse,
    WeightSummary,
    BulkOrderCreate,
    BulkOrderError,
    BulkOrderResponse,
)
from typing import List, Optional,Tuple
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

VOL_DIVIDEND_B2C = 5000


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    r = row.scalar_one_or_none()
    return r.lower() if r else None


async def _get_franchise_for_user(db: AsyncSession, user_id: str) -> Franchise | None:
    result = await db.execute(select(Franchise).where(Franchise.user_id == user_id))
    return result.scalar_one_or_none()


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    """Return franchise_id for the current user (owner or employee)."""
    if user.franchise_id:
        return user.franchise_id
    franchise = await _get_franchise_for_user(db, user.id)
    return franchise.id if franchise else None


async def _generate_order_number(db: AsyncSession) -> str:
    """Generate a sequential order number like ORD-00001."""
    count = (await db.execute(select(func.count()).select_from(Order))).scalar_one()
    return f"ORD-{str(count + 1).zfill(5)}"


def _compute_weight_summary(packages: list[OrderPackage]) -> WeightSummary:
    total_boxes = 0
    total_weight = 0.0
    total_vol = 0.0

    for pkg in packages:
        total_boxes += pkg.count
        total_weight += float(pkg.physical_weight_kg) * pkg.count
        total_vol += float(pkg.vol_weight_kg) * pkg.count

    applicable = max(total_weight, total_vol)

    return WeightSummary(
        applicable_weight_kg=round(applicable, 2),
        total_boxes=total_boxes,
        total_weight_kg=round(total_weight, 2),
        total_vol_weight_kg=round(total_vol, 2),
    )


def _build_order_out(order: Order) -> OrderOut:
    ws = _compute_weight_summary(order.packages)
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        order_type=order.order_type,
        pickup_address=PickupAddressOut.model_validate(order.pickup_address),
        consignee=ConsigneeOut.model_validate(order.consignee),
        payment_method=order.payment_method,
        cod_amount=float(order.cod_amount) if order.cod_amount is not None else None,
        to_pay_amount=float(order.to_pay_amount) if order.to_pay_amount is not None else None,
        rov=order.rov,
        order_value=float(order.order_value),
        items=[OrderItemOut.model_validate(i) for i in order.items],
        packages=[OrderPackageOut.model_validate(p) for p in order.packages],
        weight_summary=ws,
        shipping_charge=float(order.shipping_charge),
        gst_number=order.gst_number,
        eway_bill_number=order.eway_bill_number,
        barcode=order.barcode,
        status=order.status,
        created_by=order.created_by,
        franchise_id=order.franchise_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


# ── Pickup Address ─────────────────────────────────────────────────────────


async def search_pickup_addresses(
    db: AsyncSession, current_user: User, search: str | None = None
) -> PickupAddressListResponse:
    franchise_id = await _resolve_franchise_id(db, current_user)

    query = select(PickupAddress)
    count_query = select(func.count()).select_from(PickupAddress)

    if franchise_id:
        query = query.where(PickupAddress.franchise_id == franchise_id)
        count_query = count_query.where(PickupAddress.franchise_id == franchise_id)
    else:
        query = query.where(PickupAddress.user_id == current_user.id)
        count_query = count_query.where(PickupAddress.user_id == current_user.id)

    if search:
        search_filter = or_(
            PickupAddress.nickname.ilike(f"%{search}%"),
            PickupAddress.contact_name.ilike(f"%{search}%"),
            PickupAddress.address_line_1.ilike(f"%{search}%"),
            PickupAddress.city.ilike(f"%{search}%"),
            PickupAddress.pincode.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(query.order_by(PickupAddress.created_at.desc()).limit(50))
    addresses = result.scalars().all()

    return PickupAddressListResponse(
        items=[PickupAddressOut.model_validate(a) for a in addresses],
        total=total,
    )


async def create_pickup_address(
    db: AsyncSession, data: PickupAddressCreate, current_user: User
) -> PickupAddressOut:
    franchise_id = await _resolve_franchise_id(db, current_user)

    addr = PickupAddress(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        franchise_id=franchise_id,
        nickname=data.nickname,
        contact_name=data.contact_name,
        phone=data.phone,
        email=data.email,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        pincode=data.pincode,
        city=data.city,
        state=data.state,
        country=data.country,
        active=data.active,
        is_primary=data.is_primary,
    )
    db.add(addr)
    await db.flush()
    await db.refresh(addr)
    return PickupAddressOut.model_validate(addr)


async def update_pickup_address(
    db: AsyncSession, address_id: str, data: PickupAddressUpdate, current_user: User
) -> PickupAddressOut:
    result = await db.execute(select(PickupAddress).where(PickupAddress.id == address_id))
    addr = result.scalar_one_or_none()
    if not addr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pickup address not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and addr.franchise_id != franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif not franchise_id and addr.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if data.nickname is not None:
        addr.nickname = data.nickname
    if data.contact_name is not None:
        addr.contact_name = data.contact_name
    if data.phone is not None:
        addr.phone = data.phone
    if data.email is not None:
        addr.email = data.email
    if data.address_line_1 is not None:
        addr.address_line_1 = data.address_line_1
    if data.address_line_2 is not None:
        addr.address_line_2 = data.address_line_2
    if data.pincode is not None:
        addr.pincode = data.pincode
    if data.city is not None:
        addr.city = data.city
    if data.state is not None:
        addr.state = data.state
    if data.country is not None:
        addr.country = data.country
    if data.active is not None:
        addr.active = data.active
    if data.is_primary is not None:
        addr.is_primary = data.is_primary

    await db.flush()
    await db.refresh(addr)
    return PickupAddressOut.model_validate(addr)


async def delete_pickup_address(
    db: AsyncSession, address_id: str, current_user: User
) -> None:
    result = await db.execute(select(PickupAddress).where(PickupAddress.id == address_id))
    addr = result.scalar_one_or_none()
    if not addr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pickup address not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and addr.franchise_id != franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif not franchise_id and addr.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Check if address is linked to any order
    order_exists = await db.scalar(select(Order.id).where(Order.pickup_address_id == addr.id).limit(1))
    if order_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete pickup address because it is associated with one or more orders."
        )

    await db.delete(addr)
    await db.flush()


# ── Consignee ──────────────────────────────────────────────────────────────


async def search_consignees(
    db: AsyncSession, current_user: User,
    search: str | None = None,
    page: int = 1,
    limit: int = 25,
) -> ConsigneeListResponse:
    franchise_id = await _resolve_franchise_id(db, current_user)

    query = select(Consignee)
    count_query = select(func.count()).select_from(Consignee)

    if franchise_id:
        query = query.where(Consignee.franchise_id == franchise_id)
        count_query = count_query.where(Consignee.franchise_id == franchise_id)
    else:
        query = query.where(Consignee.user_id == current_user.id)
        count_query = count_query.where(Consignee.user_id == current_user.id)

    if search:
        search_filter = or_(
            Consignee.name.ilike(f"%{search}%"),
            Consignee.email.ilike(f"%{search}%"),
            Consignee.mobile.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.order_by(Consignee.created_at.desc()).offset(offset).limit(limit))
    consignees = result.scalars().all()

    return ConsigneeListResponse(
        items=[ConsigneeOut.model_validate(c) for c in consignees],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


async def create_consignee(
    db: AsyncSession, data: ConsigneeCreate, current_user: User
) -> ConsigneeOut:
    franchise_id = await _resolve_franchise_id(db, current_user)

    consignee = Consignee(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        franchise_id=franchise_id,
        name=data.name,
        mobile=data.mobile,
        alternate_mobile=data.alternate_mobile,
        email=data.email,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        pincode=data.pincode,
        city=data.city,
        state=data.state,
    )
    db.add(consignee)
    await db.flush()
    await db.refresh(consignee)
    return ConsigneeOut.model_validate(consignee)


async def update_consignee(
    db: AsyncSession, consignee_id: str, data: ConsigneeUpdate, current_user: User
) -> ConsigneeOut:
    result = await db.execute(select(Consignee).where(Consignee.id == consignee_id))
    consignee = result.scalar_one_or_none()
    if not consignee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consignee not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and consignee.franchise_id != franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif not franchise_id and consignee.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Update only provided fields
    if data.name is not None:
        consignee.name = data.name
    if data.mobile is not None:
        consignee.mobile = data.mobile
    if data.alternate_mobile is not None:
        consignee.alternate_mobile = data.alternate_mobile
    if data.email is not None:
        consignee.email = data.email
    if data.address_line_1 is not None:
        consignee.address_line_1 = data.address_line_1
    if data.address_line_2 is not None:
        consignee.address_line_2 = data.address_line_2
    if data.pincode is not None:
        consignee.pincode = data.pincode
    if data.city is not None:
        consignee.city = data.city
    if data.state is not None:
        consignee.state = data.state
    if data.status is not None:
        consignee.status = data.status

    await db.flush()
    await db.refresh(consignee)
    return ConsigneeOut.model_validate(consignee)


async def delete_consignee(
    db: AsyncSession, consignee_id: str, current_user: User
) -> None:
    result = await db.execute(select(Consignee).where(Consignee.id == consignee_id))
    consignee = result.scalar_one_or_none()
    if not consignee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consignee not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and consignee.franchise_id != franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif not franchise_id and consignee.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Check if consignee is linked to any order
    order_exists = await db.scalar(select(Order.id).where(Order.consignee_id == consignee.id).limit(1))
    if order_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete consignee because it is associated with one or more orders."
        )

    await db.delete(consignee)
    await db.flush()


# ── Order ──────────────────────────────────────────────────────────────────


async def create_order(
    db: AsyncSession, data: OrderCreate, current_user: User
) -> OrderOut:
    # Validate pickup address exists and belongs to user / franchise
    pickup = (
        await db.execute(select(PickupAddress).where(PickupAddress.id == data.pickup_address_id))
    ).scalar_one_or_none()
    if not pickup:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pickup address not found")

    # Validate consignee exists
    consignee = (
        await db.execute(select(Consignee).where(Consignee.id == data.consignee_id))
    ).scalar_one_or_none()
    if not consignee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consignee not found")
    warehouse_addresses= (
        await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == data.warehouse_addresses_id))
    ).scalar_one_or_none()
    # if not warehouse_addresses:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Warehouse not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    order_number = await _generate_order_number(db)

    # Build order
    order = Order(
        id=str(uuid.uuid4()),
        order_number=order_number,
        order_type=data.order_type.value,
        pickup_address_id=data.pickup_address_id,
        consignee_id=data.consignee_id,
        warehouse_addresses_id=data.warehouse_addresses_id,
        payment_method=data.payment_method.value,
        cod_amount=data.cod_amount,
        to_pay_amount=data.to_pay_amount,
        rov=data.rov.value,
        order_value=data.order_value,
        gst_number=data.gst_number,
        eway_bill_number=data.eway_bill_number,
        status=OrderStatus.MANIFESTED,
        created_by=current_user.id,
        franchise_id=franchise_id,
    )
    db.add(order)
    await db.flush()

    # Add items
    for item_data in data.items:
        item = OrderItem(
            id=str(uuid.uuid4()),
            order_id=order.id,
            product_name=item_data.product_name,
            sku=item_data.sku,
            unit_price=item_data.unit_price,
            qty=item_data.qty,
            total=item_data.total,
        )
        db.add(item)

    # Add packages and compute weight summary
    total_boxes = 0
    total_weight = 0.0
    total_vol = 0.0

    for pkg_data in data.packages:
        pkg = OrderPackage(
            id=str(uuid.uuid4()),
            order_id=order.id,
            count=pkg_data.count,
            length_cm=pkg_data.length_cm,
            breadth_cm=pkg_data.breadth_cm,
            height_cm=pkg_data.height_cm,
            vol_weight_kg=pkg_data.vol_weight_kg,
            physical_weight_kg=pkg_data.physical_weight_kg,
        )
        db.add(pkg)

        total_boxes += pkg_data.count
        total_weight += pkg_data.physical_weight_kg * pkg_data.count
        total_vol += pkg_data.vol_weight_kg * pkg_data.count

    applicable = max(total_weight, total_vol)

    order.total_boxes = total_boxes
    order.total_weight_kg = round(total_weight, 2)
    order.total_vol_weight_kg = round(total_vol, 2)
    order.applicable_weight_kg = round(applicable, 2)
    order.shipping_charge = data.shipping_charge

    # Generate barcode from order number
    order.barcode = generate_barcode_base64(order_number)

    await db.flush()

    # Debit wallet if shipping charge > 0 and franchise is linked
    if data.shipping_charge > 0 and franchise_id:
        await debit_for_order(db, franchise_id, order.id, data.shipping_charge)

    # Reload all columns (created_at, updated_at, etc.) + relationships
    await db.refresh(order)
    await db.refresh(order, attribute_names=["items", "packages", "pickup_address", "consignee"])

    return _build_order_out(order)


async def create_bulk_orders(
    db: AsyncSession, data: BulkOrderCreate, current_user: User
) -> BulkOrderResponse:
    """Create multiple orders in one request. Each order is processed in its own
    savepoint so a single failure does not roll back the entire batch."""
    created_orders: list[OrderOut] = []
    errors: list[BulkOrderError] = []

    for idx, order_data in enumerate(data.orders):
        try:
            async with db.begin_nested():
                order_out = await create_order(db, order_data, current_user)
                created_orders.append(order_out)
        except HTTPException as exc:
            errors.append(BulkOrderError(index=idx, error=exc.detail))
        except Exception as exc:
            logger.error(f"Bulk order index {idx} failed: {exc}")
            errors.append(BulkOrderError(index=idx, error=str(exc)))

    await db.commit()

    return BulkOrderResponse(
        total_submitted=len(data.orders),
        successful=len(created_orders),
        failed=len(errors),
        orders=created_orders,
        errors=errors,
    )


async def list_orders(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    limit: int = 10,
    search: str | None = None,
    status_filter: str | None = None,
    order_type: str | None = None,
) -> OrderListResponse:
    caller_role = await _get_caller_role_name(db, current_user.id)

    base_filters = []

    # Scope: franchise users see only their franchise orders, non-franchise see their own
    if caller_role != "super_admin":
        franchise_id = await _resolve_franchise_id(db, current_user)
        if franchise_id:
            base_filters.append(Order.franchise_id == franchise_id)
        else:
            base_filters.append(Order.created_by == current_user.id)

    if status_filter:
        base_filters.append(Order.status == status_filter)
    if order_type:
        base_filters.append(Order.order_type == order_type)

    query = select(Order).order_by(Order.created_at.desc())
    count_query = select(func.count()).select_from(Order)

    for f in base_filters:
        query = query.where(f)
        count_query = count_query.where(f)

    if search:
        search_filter = or_(
            Order.order_number.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    orders = result.scalars().all()

    items = [_build_order_out(o) for o in orders]

    return OrderListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


async def get_order(
    db: AsyncSession, order_id: str, current_user: User
) -> OrderOut:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    caller_role = await _get_caller_role_name(db, current_user.id)
    if caller_role != "super_admin":
        franchise_id = await _resolve_franchise_id(db, current_user)
        if franchise_id:
            if order.franchise_id != franchise_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        elif order.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _build_order_out(order)



async def get_filtered_orders_service(
    db: AsyncSession,
    status: Optional[OrderStatus] = None,
    limit: int = 10,
    offset: int = 0
):

    query = select(Order)

    if status:
        query = query.where(Order.status == status.value)  # important

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # fetch data
    result = await db.execute(
        query.order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    orders = result.scalars().all()

    return total, orders





