import math
import uuid
import logging
import csv
from datetime import datetime
from fastapi import Depends

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from fastapi import HTTPException, status
from sqlalchemy import select, func, or_, delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.franchise import Franchise,OrderFranchiseAddress
from app.models.pickup_address import PickupAddress
from app.models.consignee import Consignee
from app.models.warehouse import WareHouseAddress,OrderWarehouseAddress
from app.models.order import Order, OrderItem, OrderPackage, OrderStatus, BulkOrder
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
    BulkOrderOut,
    BulkOrderListResponse,
    BulkOrderError,
    BulkOrderResponse,
    OrderUpdate,
)
from typing import List, Optional,Tuple
from sqlalchemy.orm import Session

import openpyxl
from io import BytesIO
from app.schemas.rate_calculator import RateCalculationRequest, RatePackageInput
from app.services.rate_calculator.rate_calculator_service import calculate_rate
logger = logging.getLogger(__name__)

VOL_DIVIDEND_B2C = 5000


def _normalize_payment_mode(payment_method: str) -> str:
    value = str(payment_method).strip().lower().replace("_", " ")
    mapping = {
        "cod": "COD",
        "prepaid": "PREPAID",
        "to pay": "TO_PAY",
        "topay": "TO_PAY",
    }
    if value not in mapping:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported payment_method: {payment_method}")
    return mapping[value]


def _normalize_risk_type(rov: str) -> str:
    value = str(rov).strip().lower().replace(" ", "_")
    mapping = {
        "owner_risk": "OWNER_RISK",
        "carrier_risk": "CARRIER_RISK",
    }
    if value not in mapping:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported rov: {rov}")
    return mapping[value]


def _normalize_order_payment_method(payment_method: str) -> str:
    value = str(payment_method).strip().lower().replace("_", " ")
    mapping = {
        "cod": "COD",
        "prepaid": "Prepaid",
        "to pay": "To Pay",
        "topay": "To Pay",
    }
    if value not in mapping:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported payment_method: {payment_method}")
    return mapping[value]


def _normalize_order_rov(rov: str) -> str:
    value = str(rov).strip().lower().replace(" ", "_")
    mapping = {
        "owner_risk": "owner_risk",
        "carrier_risk": "carrier_risk",
    }
    if value not in mapping:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported rov: {rov}")
    return mapping[value]


async def calculate_order_shipping_charge(
    db: AsyncSession,
    *,
    order_type: str,
    pickup_pincode: str,
    delivery_pincode: str,
    payment_method: str,
    rov: str,
    order_value: float,
    packages: list,
) -> float:
    if str(order_type).strip() == "International":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rate calculation is not configured for International orders.",
        )

    def package_value(package, attr: str):
        if isinstance(package, dict):
            return package[attr]
        return getattr(package, attr)

    rate_packages = [
        RatePackageInput(
            count=int(package_value(package, "count")),
            length=float(package_value(package, "length_cm")),
            breadth=float(package_value(package, "breadth_cm")),
            height=float(package_value(package, "height_cm")),
            physical_weight=float(package_value(package, "physical_weight_kg")),
        )
        for package in packages
    ]

    request = RateCalculationRequest(
        calculator_type=str(order_type).strip(),
        pickup_pincode=str(pickup_pincode).strip(),
        delivery_pincode=str(delivery_pincode).strip(),
        shipment_type="FORWARD",
        payment_mode=_normalize_payment_mode(payment_method),
        risk_type=_normalize_risk_type(rov),
        declared_value=float(order_value or 0),
        packages=rate_packages,
    )
    rate_response = await calculate_rate(db, request)
    return float(rate_response.data.pricing.final_amount)


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
    """Generate a sequential order number safely."""
    # Find the maximum existing order number to prevent 409 Conflicts after deletions
    result = await db.execute(
        select(Order.order_number)
        .where(Order.order_number.like("ORD-%"))
        .order_by(Order.order_number.desc())
        .limit(1)
    )
    last_order = result.scalar_one_or_none()
    if not last_order:
        return "ORD-00001"
        
    try:
        last_num = int(last_order.split("-")[1])
        return f"ORD-{str(last_num + 1).zfill(5)}"
    except Exception:
        # Fallback just in case
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
    db: AsyncSession,
    current_user: User,
    search: str | None = None,
    page: int = 1,
    limit: int = 10,) -> PickupAddressListResponse:
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
    offset = (page - 1) * limit
    result = await db.execute(query.order_by(PickupAddress.created_at.desc()).offset(offset).limit(limit))
    addresses = result.scalars().all()
    return PickupAddressListResponse(
        items=[PickupAddressOut.model_validate(a) for a in addresses],
        total=total,page=page,limit=limit,total_pages=(total + limit - 1) // limit,)






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
from app.services.notification_service import create_notification

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
    
    
    warehouse_addresses = []
    for warehouse_id in data.warehouse_addresses_ids:
        warehouse = (await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == warehouse_id))).scalar_one_or_none()
        warehouse_addresses.append(warehouse) 
    
    
    franchise_addresses = []
    for franchise_id in data.franchise_addresses_ids:
        franchise = (await db.execute(select(Franchise).where(Franchise.id == franchise_id))).scalar_one_or_none()
        franchise_addresses.append(franchise) 
        
               
           
    # warehouse_addresses= (
    #     await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == data.warehouse_addresses_id))
    # ).scalar_one_or_none()
    
    
    
    
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
        payment_method=data.payment_method.value,
        cod_amount=data.cod_amount,
        to_pay_amount=data.to_pay_amount,
        rov=data.rov.value,
        order_value=data.order_value,
        gst_number=data.gst_number,
        eway_bill_number=data.eway_bill_number,
        status=OrderStatus.PROCESSING,
        previous_status=OrderStatus.PROCESSING,
        created_by=current_user.id,
        franchise_id=franchise_id,
    )
    
    
    db.add(order)
    await db.flush()
    
    
    for warehouse in warehouse_addresses:
        warehouse_map = OrderWarehouseAddress(order_id=order.id,warehouse_address_id=warehouse.id)
        db.add(warehouse_map)
    
    for franchise in franchise_addresses:
        franchise_map = OrderFranchiseAddress(order_id=order.id,franchise_address_id=franchise.id)
        db.add(franchise_map)
        
        
        
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
    shipping_charge = float(data.shipping_charge or 0)
    if shipping_charge <= 0:
        shipping_charge = await calculate_order_shipping_charge(
            db,
            order_type=data.order_type.value,
            pickup_pincode=pickup.pincode,
            delivery_pincode=consignee.pincode,
            payment_method=data.payment_method.value,
            rov=data.rov.value,
            order_value=data.order_value,
            packages=data.packages,
        )
    order.shipping_charge = shipping_charge

    # Generate barcode from order number
    order.barcode = generate_barcode_base64(order_number)

    await db.flush()

    # Debit wallet if shipping charge > 0 and franchise is linked
    if shipping_charge > 0 and franchise_id:
        await debit_for_order(db, franchise_id, order.id, shipping_charge)

    # Reload all columns (created_at, updated_at, etc.) + relationships
    await db.refresh(order)
    await create_notification(
    db=db,
    title="New Order",
    message=(f"Order {order.order_number} "f"created successfully"),type="order",order_id=order.id,)
    await db.refresh(order, attribute_names=["items", "packages", "pickup_address", "consignee"])

    return _build_order_out(order)


async def process_bulk_excel_upload(
    db: AsyncSession, 
    file_content: bytes, 
    file_name: str,
    order_type: str, 
    pickup_address_id: str, 
    current_user: User
) -> BulkOrderResponse:
    franchise_id = await _resolve_franchise_id(db, current_user)
    
    bulk_order = BulkOrder(
        id=str(uuid.uuid4()),
        file_name=file_name,
        order_type=order_type,
        pickup_address_id=pickup_address_id,
        created_by=current_user.id,
        franchise_id=franchise_id,
        status="Processing"
    )
    db.add(bulk_order)
    await db.flush()

    if file_name.lower().endswith(".csv"):
        decoded = file_content.decode("utf-8-sig")
        csv_rows = list(csv.reader(decoded.splitlines()))
        if not csv_rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is empty.")
        headers = [str(value).strip().lower() if value else "" for value in csv_rows[0]]
        data_rows = csv_rows[1:]
    else:
        wb = openpyxl.load_workbook(filename=BytesIO(file_content), data_only=True)
        sheet = wb.active
        headers = [str(cell.value).strip().lower() if cell.value else "" for cell in sheet[1]]
        data_rows = list(sheet.iter_rows(min_row=2, values_only=True))
    
    col_map = {
        "consignee_name": headers.index("consignee_name") if "consignee_name" in headers else -1,
        "mobile": headers.index("mobile") if "mobile" in headers else -1,
        "email": headers.index("email") if "email" in headers else -1,
        "address_line_1": headers.index("address_line_1") if "address_line_1" in headers else -1,
        "pincode": headers.index("pincode") if "pincode" in headers else -1,
        "city": headers.index("city") if "city" in headers else -1,
        "state": headers.index("state") if "state" in headers else -1,
        "payment_method": headers.index("payment_method") if "payment_method" in headers else -1,
        "cod_amount": headers.index("cod_amount") if "cod_amount" in headers else -1,
        "to_pay_amount": headers.index("to_pay_amount") if "to_pay_amount" in headers else -1,
        "rov": headers.index("rov") if "rov" in headers else -1,
        "order_value": headers.index("order_value") if "order_value" in headers else -1,
        "product_name": headers.index("product_name") if "product_name" in headers else -1,
        "sku": headers.index("sku") if "sku" in headers else -1,
        "unit_price": headers.index("unit_price") if "unit_price" in headers else -1,
        "qty": headers.index("qty") if "qty" in headers else -1,
        "length_cm": headers.index("length_cm") if "length_cm" in headers else -1,
        "breadth_cm": headers.index("breadth_cm") if "breadth_cm" in headers else -1,
        "height_cm": headers.index("height_cm") if "height_cm" in headers else -1,
        "physical_weight_kg": headers.index("physical_weight_kg") if "physical_weight_kg" in headers else -1,
    }

    errors = []
    success_count = 0

    for idx, row in enumerate(data_rows, start=2):
        try:
            if not any(row):
                continue
            
            async with db.begin_nested():
                def get_val(key, default=None):
                    if col_map[key] != -1 and col_map[key] < len(row) and row[col_map[key]] is not None:
                        return row[col_map[key]]
                    return default

                consignee_mobile = str(get_val("mobile", "")).strip()
                consignee_name = str(get_val("consignee_name", "")).strip()
                consignee_email = get_val("email")
                if consignee_email:
                    consignee_email = consignee_email.strip()

                # Check if consignee already exists
                query = select(Consignee).where(
                    and_(
                        Consignee.mobile == consignee_mobile,
                        Consignee.name == consignee_name
                    )
                )
                if franchise_id:
                    query = query.where(Consignee.franchise_id == franchise_id)
                else:
                    query = query.where(Consignee.user_id == current_user.id)

                existing_consignee = (await db.execute(query)).scalars().first()

                if existing_consignee:
                    consignee_id = existing_consignee.id
                else:
                    consignee_data = ConsigneeCreate(
                        name=consignee_name,
                        mobile=consignee_mobile,
                        email=consignee_email,
                        address_line_1=str(get_val("address_line_1", "")),
                        pincode=str(get_val("pincode", "")),
                        city=str(get_val("city", "")),
                        state=str(get_val("state", ""))
                    )
                    consignee_out = await create_consignee(db, consignee_data, current_user)
                    consignee_id = consignee_out.id
                
                payment_method = _normalize_order_payment_method(str(get_val("payment_method", "Prepaid")))
                order_data = OrderCreate(
                    order_type=order_type,
                    pickup_address_id=pickup_address_id,
                    consignee_id=consignee_id,
                    payment_method=payment_method,
                    cod_amount=float(get_val("cod_amount") or 0) if payment_method == "COD" else None,
                    to_pay_amount=float(get_val("to_pay_amount") or 0) if payment_method == "To Pay" else None,
                    rov=_normalize_order_rov(str(get_val("rov", "owner_risk"))),
                    order_value=float(get_val("order_value") or 0),
                    items=[
                        {
                            "product_name": str(get_val("product_name", "Product")),
                            "sku": get_val("sku"),
                            "unit_price": float(get_val("unit_price") or 0),
                            "qty": int(get_val("qty") or 1),
                            "total": float(get_val("unit_price") or 0) * int(get_val("qty") or 1)
                        }
                    ],
                    packages=[
                        {
                            "count": 1,
                            "length_cm": float(get_val("length_cm") or 1),
                            "breadth_cm": float(get_val("breadth_cm") or 1),
                            "height_cm": float(get_val("height_cm") or 1),
                            "vol_weight_kg": (float(get_val("length_cm") or 1) * float(get_val("breadth_cm") or 1) * float(get_val("height_cm") or 1)) / 5000,
                            "physical_weight_kg": float(get_val("physical_weight_kg") or 1)
                        }
                    ],
                    shipping_charge=0 
                )
                
                order_out = await create_order(db, order_data, current_user)
                
                # Update bulk_order_id directly
                order = await db.get(Order, order_out.id)
                order.bulk_order_id = bulk_order.id
                
            success_count += 1
                
        except Exception as exc:
            logger.error(f"Row {idx} failed: {str(exc)}")
            errors.append(BulkOrderError(index=idx, error=str(exc)))

    bulk_order.total_orders = success_count + len(errors)
    bulk_order.successful_orders = success_count
    bulk_order.failed_orders = len(errors)
    bulk_order.status = "Completed" if len(errors) == 0 else "Completed Errors"
    
    await db.commit()
    await db.refresh(bulk_order)
    
    return BulkOrderResponse(
        bulk_order=BulkOrderOut.model_validate(bulk_order),
        errors=errors
    )


async def list_bulk_orders(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    limit: int = 10,
) -> BulkOrderListResponse:
    franchise_id = await _resolve_franchise_id(db, current_user)
    
    query = select(BulkOrder)
    count_query = select(func.count()).select_from(BulkOrder)
    
    if franchise_id:
        query = query.where(BulkOrder.franchise_id == franchise_id)
        count_query = count_query.where(BulkOrder.franchise_id == franchise_id)
    else:
        caller_role = await _get_caller_role_name(db, current_user.id)
        if caller_role != "super_admin":
            query = query.where(BulkOrder.created_by == current_user.id)
            count_query = count_query.where(BulkOrder.created_by == current_user.id)
            
    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.order_by(BulkOrder.created_at.desc()).offset(offset).limit(limit))
    bulk_orders = result.scalars().all()
    
    return BulkOrderListResponse(
        items=[BulkOrderOut.model_validate(b) for b in bulk_orders],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )






## API for duplicating an existing order (useful for repeat shipments with same details)



async def duplicate_order(
    db: AsyncSession,
    order_id: str,
    current_user: User
) -> OrderOut:

    existing_order = (
        await db.execute(
            select(Order)
            .where(Order.id == order_id)
        )
    ).scalar_one_or_none()

    if not existing_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    existing_items = (
        await db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
    ).scalars().all()

    existing_packages = (
        await db.execute(
            select(OrderPackage).where(OrderPackage.order_id == order_id)
        )
    ).scalars().all()

    new_order_number = await _generate_order_number(db)

    franchise_id = await _resolve_franchise_id(db, current_user)

    new_order = Order(
        id=str(uuid.uuid4()),
        order_number=new_order_number,
        order_type=existing_order.order_type,
        pickup_address_id=existing_order.pickup_address_id,
        consignee_id=existing_order.consignee_id,
        warehouse_addresses_id=existing_order.warehouse_addresses_id,
        payment_method=existing_order.payment_method,
        cod_amount=existing_order.cod_amount,
        to_pay_amount=existing_order.to_pay_amount,
        rov=existing_order.rov,
        order_value=existing_order.order_value,
        gst_number=existing_order.gst_number,
        eway_bill_number=existing_order.eway_bill_number,
        shipping_charge=existing_order.shipping_charge,
        total_boxes=existing_order.total_boxes,
        total_weight_kg=existing_order.total_weight_kg,
        total_vol_weight_kg=existing_order.total_vol_weight_kg,
        applicable_weight_kg=existing_order.applicable_weight_kg,
        status=OrderStatus.PROCESSING,
        created_by=current_user.id,
        franchise_id=franchise_id,
    )

    new_order.barcode = generate_barcode_base64(new_order_number)

    db.add(new_order)
    await db.flush()

    for item in existing_items:
        new_item = OrderItem(
            id=str(uuid.uuid4()),
            order_id=new_order.id,
            product_name=item.product_name,
            sku=item.sku,
            unit_price=item.unit_price,
            qty=item.qty,
            total=item.total,
        )
        db.add(new_item)

    for pkg in existing_packages:
        new_pkg = OrderPackage(
            id=str(uuid.uuid4()),
            order_id=new_order.id,
            count=pkg.count,
            length_cm=pkg.length_cm,
            breadth_cm=pkg.breadth_cm,
            height_cm=pkg.height_cm,
            vol_weight_kg=pkg.vol_weight_kg,
            physical_weight_kg=pkg.physical_weight_kg,
        )
        db.add(new_pkg)

    await db.flush()

    if new_order.shipping_charge > 0 and franchise_id:
        await debit_for_order(
            db,
            franchise_id,
            new_order.id,
            new_order.shipping_charge
        )

    await db.refresh(new_order)
    await db.refresh(
        new_order,
        attribute_names=[
            "items",
            "packages",
            "pickup_address",
            "consignee"
        ]
    )

    return _build_order_out(new_order)


# async def list_orders(
#     db: AsyncSession,
#     current_user: User,
#     page: int = 1,
#     limit: int = 10,
#     search: str | None = None,
#     status_filter: str | None = None,
#     order_type: str | None = None,
# ) -> OrderListResponse:
#     caller_role = await _get_caller_role_name(db, current_user.id)

#     base_filters = []

#     # Scope: franchise users see only their franchise orders, non-franchise see their own
#     if caller_role != "super_admin":
#         franchise_id = await _resolve_franchise_id(db, current_user)
#         if franchise_id:
#             base_filters.append(Order.franchise_id == franchise_id)
#         else:
#             base_filters.append(Order.created_by == current_user.id)

#     if status_filter:
#         base_filters.append(Order.status == status_filter)
#     if order_type:
#         base_filters.append(Order.order_type == order_type)

#     query = select(Order).order_by(Order.created_at.desc())
#     count_query = select(func.count()).select_from(Order)

#     for f in base_filters:
#         query = query.where(f)
#         count_query = count_query.where(f)

#     if search:
#         search_filter = or_(
#             Order.order_number.ilike(f"%{search}%"),
#         )
#         query = query.where(search_filter)
#         count_query = count_query.where(search_filter)

#     total = (await db.execute(count_query)).scalar_one()
#     offset = (page - 1) * limit
#     result = await db.execute(query.offset(offset).limit(limit))
#     orders = result.scalars().all()

#     items = [_build_order_out(o) for o in orders]

#     return OrderListResponse(
#         items=items,
#         total=total,
#         page=page,
#         limit=limit,
#         pages=math.ceil(total / limit) if total > 0 else 0,
#     )


async def list_orders(
    db: AsyncSession,
    current_user: User,

    page: int = 1,
    limit: int = 25,

    start_date: datetime | None = None,
    end_date: datetime | None = None,

    order_id: str | None = None,
    awb_no: str | None = None,
    buyer_name: str | None = None,

    payment_method: str | None = None,
    status_filter: str | None = None,
    bulk_order_id: str | None = None,
) -> dict:

    filters = []

    if bulk_order_id:
        filters.append(Order.bulk_order_id == bulk_order_id)

    caller_role = await _get_caller_role_name(
        db,
        current_user.id
    )

    if caller_role != "super_admin":

        franchise_id = await _resolve_franchise_id(
            db,
            current_user
        )

        if franchise_id:
            filters.append(
                Order.franchise_id == franchise_id
            )
        else:
            filters.append(
                Order.created_by == current_user.id
            )

   

    if start_date:
        filters.append(
            Order.created_at >= start_date
        )

    if end_date:
        filters.append(
            Order.created_at <= end_date
        )

    

    if order_id:
        filters.append(
            Order.order_number.ilike(
                f"%{order_id}%"
            )
        )

    

    if awb_no:
        filters.append(
            Order.barcode.ilike(
                f"%{awb_no}%"
            )
        )

    

    if buyer_name:
        filters.append(
            Consignee.name.ilike(
                f"%{buyer_name}%"
            )
        )

    

    if (
        payment_method
        and payment_method != "All"
    ):
        filters.append(
            Order.payment_method == payment_method
        )

    
    if (
        status_filter
        and status_filter != "All"
    ):
        filters.append(
            Order.status == status_filter
        )

    

    query = (
        select(Order)
        .join(Consignee, Order.consignee_id == Consignee.id)
        .where(and_(*filters))
        .order_by(Order.created_at.desc())
    )

    

    count_query = (
        select(func.count())
        .select_from(Order)
        .join(Consignee, Order.consignee_id == Consignee.id)
        .where(and_(*filters))
    )

    

    offset = (page - 1) * limit

    result = await db.execute(
        query.offset(offset).limit(limit)
    )

    orders = result.scalars().all()

    total = (
        await db.execute(count_query)
    ).scalar_one()

    

    status_count_query = (
        select(
            Order.status,
            func.count(Order.id)
        )
        .select_from(Order)
        .join(Consignee, Order.consignee_id == Consignee.id)
        .where(and_(*filters))
        .group_by(Order.status)
    )

    status_result = await db.execute(
        status_count_query
    )

    raw_status_counts = {
        row[0]: row[1]
        for row in status_result.all()
    }

    

    all_statuses = [
        "Processing",
        "Manifested",
        "Picked",
        "Not Picked",
        "In_transit",
        "Ndr",
        "Ofd",
        "Delivered",
        "Rto_in_transit",
        "Rto_delivered",
        "Returned",
        "Cancelled",
        "Lost",
    ]

    status_counts = {
        status: raw_status_counts.get(status, 0)
        for status in all_statuses
    }

    

    items = [
        _build_order_out(order)
        for order in orders
    ]

   

    return {
        "items": items,

        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (
                math.ceil(total / limit)
                if total > 0
                else 0
            ),
        },

        "status_counts": status_counts,
    }



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



# import base64

# from fastapi import HTTPException, status

# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.models.order import Order
# from app.models.user import User

# from app.schemas.order import OrderOut





# async def get_order_bybarcode(db: AsyncSession,barcode: str,current_user: User,) -> OrderOut:
#     decoded_input = barcode.strip()
#     try:
#         decoded_input = base64.b64decode(decoded_input).decode("utf-8")
#     except Exception:
#         pass
#     stmt = select(Order).where((Order.barcode == decoded_input)|(Order.order_number == decoded_input))
#     result = await db.execute(stmt)
#     order = result.scalar_one_or_none()
#     if not order:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Order not found")
#     caller_role = await _get_caller_role_name(db,current_user.id)
#     if caller_role != "super_admin":
#         franchise_id = await _resolve_franchise_id(db,current_user)
#         if franchise_id:
#             if order.franchise_id != franchise_id:
#                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Access denied")
#         elif order.created_by != current_user.id:
#             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Access denied")
#     return _build_order_out(order)

import base64

from fastapi import HTTPException, status

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.user import User

from app.schemas.order import OrderOut


async def get_order_bybarcode(db: AsyncSession,barcode: str,current_user: User,) -> OrderOut:
    decoded_input = barcode.strip()
    try:
        decoded_input = base64.b64decode(decoded_input).decode("utf-8")
    except Exception:
        pass
    stmt = select(Order).where(((Order.barcode == decoded_input)|(Order.order_number == decoded_input)))
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Order not found")
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



## Order Update API


# async def update_order(
#     db: AsyncSession,
#     order_id: str,
#     data: OrderUpdate,
#     current_user: User
# ) -> OrderOut:

#     order = (
#         await db.execute(
#             select(Order)
#             .where(Order.id == order_id)
#         )
#     ).scalar_one_or_none()

#     if not order:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Order not found"
#         )

#     if data.pickup_address_id:
#         pickup = (
#             await db.execute(
#                 select(PickupAddress).where(
#                     PickupAddress.id == data.pickup_address_id
#                 )
#             )
#         ).scalar_one_or_none()

#         if not pickup:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Pickup address not found"
#             )

#         order.pickup_address_id = data.pickup_address_id

#     if data.consignee_id:
#         consignee = (
#             await db.execute(
#                 select(Consignee).where(
#                     Consignee.id == data.consignee_id
#                 )
#             )
#         ).scalar_one_or_none()

#         if not consignee:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Consignee not found"
#             )

#         order.consignee_id = data.consignee_id

#     if data.warehouse_addresses_id:
#         warehouse = (
#             await db.execute(
#                 select(WareHouseAddress).where(
#                     WareHouseAddress.id == data.warehouse_addresses_id
#                 )
#             )
#         ).scalar_one_or_none()

#         if not warehouse:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Warehouse not found"
#             )

#         order.warehouse_addresses_id = data.warehouse_addresses_id

#     if data.order_type:
#         order.order_type = data.order_type.value

#     if data.payment_method:
#         order.payment_method = data.payment_method.value

#     if data.rov:
#         order.rov = data.rov.value

#     order.cod_amount = data.cod_amount
#     order.to_pay_amount = data.to_pay_amount
#     order.order_value = data.order_value
#     order.gst_number = data.gst_number
#     order.eway_bill_number = data.eway_bill_number
#     order.shipping_charge = data.shipping_charge

    
#     if data.items is not None:

#         await db.execute(
#             delete(OrderItem).where(OrderItem.order_id == order.id)
#         )

#         for item_data in data.items:
#             item = OrderItem(
#                 id=str(uuid.uuid4()),
#                 order_id=order.id,
#                 product_name=item_data.product_name,
#                 sku=item_data.sku,
#                 unit_price=item_data.unit_price,
#                 qty=item_data.qty,
#                 total=item_data.total,
#             )
#             db.add(item)

#     # -------------------------
#     # Update Packages
#     # -------------------------
#     total_boxes = 0
#     total_weight = 0.0
#     total_vol = 0.0

#     if data.packages is not None:

#         # Delete existing packages
#         await db.execute(
#             delete(OrderPackage).where(OrderPackage.order_id == order.id)
#         )

#         # Add new packages
#         for pkg_data in data.packages:

#             pkg = OrderPackage(
#                 id=str(uuid.uuid4()),
#                 order_id=order.id,
#                 count=pkg_data.count,
#                 length_cm=pkg_data.length_cm,
#                 breadth_cm=pkg_data.breadth_cm,
#                 height_cm=pkg_data.height_cm,
#                 vol_weight_kg=pkg_data.vol_weight_kg,
#                 physical_weight_kg=pkg_data.physical_weight_kg,
#             )

#             db.add(pkg)

#             total_boxes += pkg_data.count
#             total_weight += (
#                 pkg_data.physical_weight_kg * pkg_data.count
#             )
#             total_vol += (
#                 pkg_data.vol_weight_kg * pkg_data.count
#             )

#         applicable = max(total_weight, total_vol)

#         order.total_boxes = total_boxes
#         order.total_weight_kg = round(total_weight, 2)
#         order.total_vol_weight_kg = round(total_vol, 2)
#         order.applicable_weight_kg = round(applicable, 2)

#     # Regenerate barcode if needed
#     order.barcode = generate_barcode_base64(order.order_number)

#     await db.commit()

#     # Refresh relationships
#     await db.refresh(order)
#     await db.refresh(
#         order,
#         attribute_names=[
#             "items",
#             "packages",
#             "pickup_address",
#             "consignee"
#         ]
#     )

#     return _build_order_out(order)



async def update_order(
    db: AsyncSession,
    order_id: str,
    data: OrderUpdate,
    current_user: User
) -> OrderOut:

    print("Updating order:", order_id)
    order = (
        await db.execute(
            select(Order).where(Order.id == order_id)
        )
    ).scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )


    if data.pickup_address_id:

        pickup = (
            await db.execute(
                select(PickupAddress).where(
                    PickupAddress.id == data.pickup_address_id
                )
            )
        ).scalar_one_or_none()

        if not pickup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pickup address not found"
            )

        order.pickup_address_id = data.pickup_address_id

    
    if data.consignee_id:

        consignee = (
            await db.execute(
                select(Consignee).where(
                    Consignee.id == data.consignee_id
                )
            )
        ).scalar_one_or_none()

        if not consignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Consignee not found"
            )

        order.consignee_id = data.consignee_id

    
    if data.warehouse_addresses_id:

        warehouse = (
            await db.execute(
                select(WareHouseAddress).where(
                    WareHouseAddress.id == data.warehouse_addresses_id
                )
            )
        ).scalar_one_or_none()

        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse not found"
            )

        order.warehouse_addresses_id = data.warehouse_addresses_id

    

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():

        # Skip separately handled fields
        if field in [
            "items",
            "packages",
            "pickup_address_id",
            "consignee_id",
            "warehouse_addresses_id",
        ]:
            continue

        # Handle enum values
        if field in ["order_type", "payment_method", "rov"]:
            setattr(order, field, value.value)

        else:
            setattr(order, field, value)

    

    if data.items is not None:

        # Delete old items
        await db.execute(
            delete(OrderItem).where(
                OrderItem.order_id == order.id
            )
        )

        # Add new items
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

    

    if data.packages is not None:

        # Delete old packages
        await db.execute(
            delete(OrderPackage).where(
                OrderPackage.order_id == order.id
            )
        )

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

            total_weight += (
                pkg_data.physical_weight_kg * pkg_data.count
            )

            total_vol += (
                pkg_data.vol_weight_kg * pkg_data.count
            )

        applicable = max(total_weight, total_vol)

        order.total_boxes = total_boxes
        order.total_weight_kg = round(total_weight, 2)
        order.total_vol_weight_kg = round(total_vol, 2)
        order.applicable_weight_kg = round(applicable, 2)

    

    order.barcode = generate_barcode_base64(
        order.order_number
    )

    
    await db.commit()

    

    await db.refresh(order)

    await db.refresh(
        order,
        attribute_names=[
            "items",
            "packages",
            "pickup_address",
            "consignee",
        ]
    )
    return _build_order_out(order)





## Delete Order API

async def delete_order(
    db: AsyncSession,
    order_id: str,
    current_user: User
):

    

    order = (
        await db.execute(
            select(Order).where(Order.id == order_id)
        )
    ).scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    

    await db.execute(
        delete(OrderItem).where(
            OrderItem.order_id == order.id
        )
    )

    await db.execute(
        delete(OrderPackage).where(
            OrderPackage.order_id == order.id
        )
    )

    

    await db.delete(order)

    
    await db.commit()

    return {
        "success": True,
        "message": "Order deleted successfully"
    }




async def get_order_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),):
    total_query = select(func.count(Order.id))
    status_query = (select(Order.status,func.count(Order.id)).group_by(Order.status))
    if current_user.role_name != "super_admin":
        franchise_id = await _resolve_franchise_id(db,current_user)
        if franchise_id:
            total_query = total_query.where(Order.franchise_id == franchise_id)
            status_query = status_query.where(Order.franchise_id == franchise_id)
    total_orders = await db.scalar(total_query)
    result = await db.execute(status_query)
    rows = result.all()
    status_counts = {
        status.value: 0 for status in OrderStatus
    }
    for status, count in rows:
        key = status.value if hasattr(status, "value") else status
        status_counts[key] = count
    return {
        "total_orders": total_orders or 0,
        "status_counts": status_counts
    }