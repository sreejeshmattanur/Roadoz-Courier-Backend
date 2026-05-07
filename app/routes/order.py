import base64
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User

from app.models.order import Order,OrderItem,OrderPackage
from app.models.warehouse import WareHouseAddress

from app.models.order import OrderStatus

from app.schemas.order import (
    PickupAddressCreate,
    PickupAddressOut,
    PickupAddressListResponse,
    ConsigneeCreate,
    ConsigneeOut,
    ConsigneeListResponse,
    OrderCreate,
    OrderOut,
    OrderListResponse,
    BulkOrderCreate,
    BulkOrderResponse,
    LocationRequest,
    OrderStatusListResponse,

)
from app.services.order_service import (
    search_pickup_addresses,
    create_pickup_address,
    search_consignees,
    create_consignee,
    create_order,
    create_bulk_orders,
    list_orders,
    get_order,
    get_filtered_orders_service
)

from sqlalchemy.orm import Session
from datetime import datetime, timedelta


import base64
from datetime import datetime, timedelta
from io import BytesIO

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from PIL import Image
from pyzbar.pyzbar import decode
import httpx
from app.models.order import Order, ConsigneeToDelivery, PickupToConsignees,WarehouseToDelivery

from datetime import datetime, date
from sqlalchemy import select, func, or_
from enum import Enum 
from app.schemas.order import TodayStatusRequest,OrderStatusRequest 




router = APIRouter(prefix="/orders", tags=["Orders"])


# ── Pickup Addresses ───────────────────────────────────────────────────────


@router.get("/pickup-addresses", response_model=PickupAddressListResponse)
async def search_pickup_addresses_endpoint(
    search: Optional[str] = Query(None, description="Search by nickname, contact name, address, city, or pincode"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("pickup_addresses:view")),
):
    return await search_pickup_addresses(db, current_user, search=search)


@router.post("/pickup-addresses", response_model=PickupAddressOut, status_code=201)
async def create_pickup_address_endpoint(
    data: PickupAddressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("pickup_addresses:create")),
):
    return await create_pickup_address(db, data, current_user)


# ── Consignees ─────────────────────────────────────────────────────────────


@router.get("/consignees", response_model=ConsigneeListResponse)
async def search_consignees_endpoint(
    search: Optional[str] = Query(None, description="Search by name, email, or mobile"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:view")),
):
    return await search_consignees(db, current_user, search=search)


@router.post("/consignees", response_model=ConsigneeOut, status_code=201)
async def create_consignee_endpoint(
    data: ConsigneeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:create")),
):
    return await create_consignee(db, data, current_user)


# ── Orders ─────────────────────────────────────────────────────────────────


@router.post("", response_model=OrderOut, status_code=201)
async def create_order_endpoint(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:create")),
):
    return await create_order(db, data, current_user)


@router.post("/bulk", response_model=BulkOrderResponse, status_code=200)
async def create_bulk_orders_endpoint(
    data: BulkOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:create")),
):
    return await create_bulk_orders(db, data, current_user)


@router.get("", response_model=OrderListResponse)
async def list_orders_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by order number"),
    status: Optional[str] = Query(None, description="Filter by status"),
    order_type: Optional[str] = Query(None, description="Filter by order type (B2C, B2B, International)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return await list_orders(
        db, current_user, page=page, limit=limit,
        search=search, status_filter=status, order_type=order_type,
    )

@router.get("/status", response_model=OrderStatusListResponse)
async def get_filtered_orders_endpoint(
    status: Optional[OrderStatus] = Query(None),
    limit: int = Query(10, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    total, orders = await get_filtered_orders_service(db, status, limit, offset)

    return {
        "total": total,
        "status_filter": status,
        "data": orders
    }




# utils/barcode_utils.py

import base64
import uuid
from io import BytesIO

from PIL import Image
from pyzbar.pyzbar import decode

import barcode
from barcode.writer import ImageWriter


# 1. Generate 8-char unique public ID
def generate_public_id():
    return str(uuid.uuid4()).replace("-", "")[:8].upper()


# 2. Decode EXISTING barcode image -> get original value
def decode_barcode_from_base64(barcode_base64: str) -> str:
    image_data = base64.b64decode(barcode_base64)
    image = Image.open(BytesIO(image_data))

    decoded_objects = decode(image)
    if not decoded_objects:
        raise Exception("Barcode not readable")

    return decoded_objects[0].data.decode("utf-8")


# 3. Generate NEW barcode image from public ID
def generate_barcode_image(value: str) -> str:
    CODE128 = barcode.get_barcode_class("code128")
    my_code = CODE128(value, writer=ImageWriter())

    buffer = BytesIO()
    my_code.write(buffer)

    return base64.b64encode(buffer.getvalue()).decode()


# 4. Main function (IMPORTANT)
def create_mapped_barcode(old_barcode_base64: str):
    # decode original barcode
    original_value = decode_barcode_from_base64(old_barcode_base64)

    # create new public ID
    public_id = generate_public_id()

    # generate new barcode image using public_id
    new_barcode_image = generate_barcode_image(public_id)

    return {
        "public_id": public_id,           # new 8-char code (used for scanning)
        "original_value": original_value, # old barcode value (hidden/internal)
        "barcode_image": new_barcode_image
    }







@router.get("/{order_id}/barcode")
async def get_order_barcode_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    order = await get_order(db, order_id, current_user)
    if not order.barcode:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Barcode not available")
    png_bytes = base64.b64decode(order.barcode)
    return Response(content=png_bytes, media_type="image/png")











@router.get("/{order_id}", response_model=OrderOut)
async def get_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return await get_order(db, order_id, current_user)





PENDING = "pending"
DISPATCHED = "dispatched"
DELIVERED = "delivered"
CANCELLED = "cancelled"


@router.get("/scan/{barcode}")
async def scan_order(
    barcode: str,
    db: AsyncSession = Depends(get_db),   # 👈 IMPORTANT (AsyncSession)
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view"))
):
    decoded_input = barcode.strip()
    try:
        decoded_input = base64.b64decode(decoded_input).decode("utf-8")
    except Exception:
        pass
    stmt = select(Order).where(
        (Order.barcode == decoded_input) |
        (Order.order_number == decoded_input)
    )

    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        result = await db.execute(select(Order))
        all_orders = result.scalars().all()

        for o in all_orders:
            if not o.barcode:
                continue

            try:
                img_data = base64.b64decode(o.barcode)
                img = Image.open(BytesIO(img_data))

                decoded = decode(img)

                for b in decoded:
                    value = b.data.decode("utf-8")

                    if value == decoded_input:
                        order = o
                        break

                if order:
                    break

            except Exception:
                continue
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    now = datetime.utcnow()
    if order.status not in [DELIVERED, CANCELLED]:
        if now - order.created_at > timedelta(hours=24):
            order.status = CANCELLED
            await db.commit()
            await db.refresh(order)

            return {
                "message": "Auto cancelled (24h expired)",
                "barcode": order.barcode,
                "status": order.status
            }
    if order.status == PENDING:
        order.status = DISPATCHED

    elif order.status == DISPATCHED:
        order.status = DELIVERED

    elif order.status == DELIVERED:
        return {"message": "Already delivered", "status": order.status}

    elif order.status == CANCELLED:
        return {"message": "Order cancelled", "status": order.status}

    await db.commit()
    await db.refresh(order)

    return {
        "barcode": order.barcode,
        "order_number": order.order_number,
        "status": order.status,
        "updated_at": now
    }
    
    


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException


@router.get("/order/full/{barcode}")
async def get_full_order(
    barcode: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view"))
):

    decoded_input = barcode.strip()

    try:
        decoded_input = base64.b64decode(decoded_input).decode("utf-8")
    except Exception:
        pass
    stmt = select(Order).where(
        (Order.barcode == decoded_input) |
        (Order.order_number == decoded_input)
    )

    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"Order not found: {decoded_input}"
        )
    items_result = await db.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    )
    items = items_result.scalars().all()
    packages_result = await db.execute(
        select(OrderPackage).where(OrderPackage.order_id == order.id)
    )
    packages = packages_result.scalars().all()
    return {
        "barcode": order.barcode,
        "order_number": order.order_number,
        "status": order.status,

        "order": {
            "id": order.id,
            "order_type": order.order_type,
            "payment_method": order.payment_method,
            "cod_amount": float(order.cod_amount) if order.cod_amount else None,
            "to_pay_amount": float(order.to_pay_amount) if order.to_pay_amount else None,
            "order_value": float(order.order_value),
            "shipping_charge": float(order.shipping_charge),
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        },

        "items": [
            {
                "id": i.id,
                "product_name": i.product_name,
                "sku": i.sku,
                "unit_price": float(i.unit_price),
                "qty": i.qty,
                "total": float(i.total),
            }
            for i in items
        ],

        "packages": [
            {
                "id": p.id,
                "count": p.count,
                "length_cm": float(p.length_cm),
                "breadth_cm": float(p.breadth_cm),
                "height_cm": float(p.height_cm),
                "vol_weight_kg": float(p.vol_weight_kg),
                "physical_weight_kg": float(p.physical_weight_kg),
            }
            for p in packages
        ]
    }
    
    








async def get_pincode_from_lat_lng(lat: float, lng: float):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"User-Agent": "courier-app"})
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            return {
                "pincode": address.get("postcode"),
                "city": address.get("city") or address.get("town") or address.get("village"),
                "state": address.get("state"),
                "country": address.get("country"),
            }
        return None
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return None


@router.post("/get-pincode/{barcode}")
async def get_pincode_from_gps(
    barcode: str,
    location: LocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    decoded_barcode = barcode.strip()
    try:
        decoded_barcode = base64.b64decode(decoded_barcode).decode("utf-8")
    except Exception:
        pass

    # Get GPS pincode — dict or None
    gps_data = await get_pincode_from_lat_lng(location.lat, location.lng)
    print("GPS DATA:", gps_data)
    # ERROR FIX 4: handle None from failed GPS lookup
    if not gps_data or not gps_data.get("pincode"):
        raise HTTPException(status_code=400, detail="Could not determine pincode from GPS location")

    gps_pincode = gps_data["pincode"]  # ERROR FIX 3: dict access, not attribute
    stmt = select(Order).where(Order.order_number == decoded_barcode)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    pickup = order.pickup_address
    consignee = order.consignee
    warehouseaddress=order.warehouseaddress

    if not pickup:
        raise HTTPException(status_code=404, detail="Pickup address not found")
    if not consignee:
        raise HTTPException(status_code=404, detail="Consignee not found")
    # if not warehouseaddress:
    #     raise HTTPException(status_code=404, detail="Warehouseaddress not found")
    
    

    if pickup.pincode == gps_pincode:

        existing_stmt = select(PickupToConsignees).where(PickupToConsignees.order_id == order.id)
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=409, detail="Pickup to consignee record already exists for this order")

        pickup_to_consignee = PickupToConsignees(
            pincode=pickup.pincode,
            status=OrderStatus.PICKED,
            order_id=order.id,
            pickup_addresses_id=pickup.id,
            user_id=current_user.id  
        )
        db.add(pickup_to_consignee)
        order.status = OrderStatus.PICKED
        order.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(pickup_to_consignee)

        return {
            "stage": "Picked",
            "order_id": order.id,
            "user_id":current_user.id, 
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": pickup_to_consignee.id,
            "pickup_address_id": pickup.id,
            "pincode": pickup.pincode,
            "city": pickup.city,
            "state": pickup.state,
            "address": pickup.address_line_1,
            "contact_name": pickup.contact_name,
            "phone": pickup.phone,
            "gps_pincode": gps_pincode,
        }
        

    elif warehouseaddress and warehouseaddress.pincode == gps_pincode:
        existing_stmt = select(WarehouseToDelivery).where(WarehouseToDelivery.order_id == order.id)
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=409, detail="Warehouseaddress to consignee record already exists for this order")

        pickup_to_consignee = WarehouseToDelivery(
            pincode=warehouseaddress.pincode,
            status=OrderStatus.DISPATCHED,
            order_id=order.id,
            warehouse_addresses_id=warehouseaddress.id,
            user_id=current_user.id 
        )
        db.add(pickup_to_consignee)
        order.status = OrderStatus.DISPATCHED
        order.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(pickup_to_consignee)

        return {
            "stage": "Dispatched",
            "order_id": order.id,
            "user_id":current_user.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": warehouseaddress.id,
            "warehouseaddress_address_id": warehouseaddress.id,
            "pincode": warehouseaddress.pincode,
            "city": warehouseaddress.city,
            "state": warehouseaddress.state,
            "address": warehouseaddress.address_line_1,
            "contact_name": warehouseaddress.contact_name,
            "phone": warehouseaddress.phone,
            "gps_pincode": gps_pincode,
        }
        
 
    elif consignee.pincode == gps_pincode:
        print("gps_pincode",gps_pincode)
        
        existing_stmt = select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order.id)
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=409, detail="ConsigneeToDelivery record already exists for this order")
        
        consignee_to_delivery = ConsigneeToDelivery(
            pincode=consignee.pincode,
            status=OrderStatus.DELIVERED,
            order_id=order.id,
            consignee_id=consignee.id,
            user_id=current_user.id 
        )
        db.add(consignee_to_delivery)
        order.status = OrderStatus.DELIVERED
        order.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(consignee_to_delivery)

        return {
            "stage": "Delivery",
            "order_id": order.id,
            "user_id":current_user.id ,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": consignee_to_delivery.id,
            "consignee_id": consignee.id,
            "pincode": consignee.pincode,
            "consignee_name": consignee.name,
            "consignee_phone": consignee.mobile,
            "consignee_address": consignee.address_line_1,
            "consignee_city": consignee.city,
            "consignee_state": consignee.state,
            "gps_pincode": gps_pincode,
        }

    else:
        raise HTTPException(status_code=400, detail="GPS location does not match pickup or consignee pincode")

from enum import Enum as PyEnum

class FilterableStatus(str, PyEnum):
    DISPATCHED = "Dispatched"
    PICKED = "Picked"
    CANCELLED = "Cancelled"
    DELIVERED = "Delivered"








    
class FilterableStatus(str, Enum):
    DISPATCHED = "Dispatched"
    PICKED = "Picked"
    CANCELLED = "Cancelled"
    DELIVERED = "Delivered"

       
@router.post("/orders/today-status")
async def get_today_status_orders(
    payload: TodayStatusRequest,
    status: FilterableStatus = Query(..., description="Dispatched | Picked | Cancelled | Delivered"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),):
    
    today = payload.date
    offset = (page - 1) * limit

    consignee_order_ids = (
        select(ConsigneeToDelivery.order_id)
        .where(
            ConsigneeToDelivery.user_id == current_user.id,
            func.date(ConsigneeToDelivery.updated_at) == today
        )
    )
    pickup_order_ids = (
        select(PickupToConsignees.order_id)
        .where(
            PickupToConsignees.user_id == current_user.id,
            func.date(PickupToConsignees.updated_at) == today
        )
    )
    warehouse_order_ids = (
        select(WarehouseToDelivery.order_id)
        .where(
            WarehouseToDelivery.user_id == current_user.id,
            func.date(WarehouseToDelivery.updated_at) == today
        )
    )

    base_filter = [
        Order.created_by == current_user.id,
        Order.status == status.value,
        or_(
            Order.id.in_(consignee_order_ids),
            Order.id.in_(pickup_order_ids),
            Order.id.in_(warehouse_order_ids),
        )
    ]

    # Get total count
    count_stmt = select(func.count()).select_from(Order).where(*base_filter)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Get paginated orders
    stmt = (
        select(Order)
        .where(*base_filter)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit))
    result = await db.execute(stmt)
    orders = result.scalars().all()
    if not orders:
        raise HTTPException(status_code=404,detail=f"No orders with status '{status.value}' updated today ({today})")
    total_pages = (total + limit - 1) // limit  
    return {
        "date": str(today),
        "status": status.value,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "order_type": o.order_type,
                "created_by": o.created_by,
                "status": o.status,
                "payment_method": o.payment_method,
                "cod_amount": float(o.cod_amount) if o.cod_amount else None,
                "order_value": float(o.order_value),
                "total_weight_kg": float(o.total_weight_kg),
                "applicable_weight_kg": float(o.applicable_weight_kg),
                "shipping_charge": float(o.shipping_charge),
                "total_boxes": o.total_boxes,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
                "items": [
                    {
                        "product_name": item.product_name,
                        "sku": item.sku,
                        "unit_price": float(item.unit_price),
                        "qty": item.qty,
                        "total": float(item.total),
                    }
                    for item in o.items
                ],
                "packages": [
                    {
                        "count": pkg.count,
                        "length_cm": float(pkg.length_cm),
                        "breadth_cm": float(pkg.breadth_cm),
                        "height_cm": float(pkg.height_cm),
                        "physical_weight_kg": float(pkg.physical_weight_kg),
                        "vol_weight_kg": float(pkg.vol_weight_kg),
                    }
                    for pkg in o.packages
                ],
                "pickup_address": {
                    "id": o.pickup_address.id,
                } if o.pickup_address else None,
                "consignee": {
                    "id": o.consignee.id,
                    "name": o.consignee.name,
                } if o.consignee else None,
            }
            for o in orders
        ]
    }    
    
    
   

@router.get("/orders/by-status")
async def get_all_orders_by_status(
    payload: OrderStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),):
    offset = (payload.page - 1) * payload.limit
    base_filter = [Order.status == payload.status.value]
    count_stmt = select(func.count()).select_from(Order).where(*base_filter)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Paginated orders
    stmt = (
        select(Order)
        .where(*base_filter)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(payload.limit)
    )

    result = await db.execute(stmt)
    orders = result.scalars().all()

    if not orders:
        raise HTTPException(
            status_code=404,
            detail=f"No orders found with status '{payload.status.value}'"
        )

    total_pages = (total + payload.limit - 1) // payload.limit

    return {
        "status": payload.status.value,
        "pagination": {
            "page": payload.page,
            "limit": payload.limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": payload.page < total_pages,
            "has_prev": payload.page > 1,
        },
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "order_type": o.order_type,
                "status": o.status,
                "created_by": o.created_by,
                "payment_method": o.payment_method,
                "cod_amount": float(o.cod_amount) if o.cod_amount else None,
                "order_value": float(o.order_value),
                "total_weight_kg": float(o.total_weight_kg),
                "applicable_weight_kg": float(o.applicable_weight_kg),
                "shipping_charge": float(o.shipping_charge),
                "total_boxes": o.total_boxes,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
                "items": [
                    {
                        "product_name": item.product_name,
                        "sku": item.sku,
                        "unit_price": float(item.unit_price),
                        "qty": item.qty,
                        "total": float(item.total),
                    }
                    for item in o.items
                ],
                "packages": [
                    {
                        "count": pkg.count,
                        "length_cm": float(pkg.length_cm),
                        "breadth_cm": float(pkg.breadth_cm),
                        "height_cm": float(pkg.height_cm),
                        "physical_weight_kg": float(pkg.physical_weight_kg),
                        "vol_weight_kg": float(pkg.vol_weight_kg),
                    }
                    for pkg in o.packages
                ],
                "pickup_address": {
                    "id": o.pickup_address.id,
                } if o.pickup_address else None,
                "consignee": {
                    "id": o.consignee.id,
                    "name": o.consignee.name,
                } if o.consignee else None,
            }
            for o in orders
        ]
    }   
    
    
    
    