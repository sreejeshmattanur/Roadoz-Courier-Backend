import base64
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status, File, UploadFile, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User

from app.models.order import Order,OrderItem,OrderPackage
from app.models.warehouse import WareHouseAddress,OrderWarehouseAddress

from app.models.order import OrderStatus,BagOrder,Bag
import pytz
IST = pytz.timezone("Asia/Kolkata")
from app.schemas.order import (
    PickupAddressCreate,
    PickupAddressUpdate,
    PickupAddressOut,
    PickupAddressListResponse,
    ConsigneeCreate,
    ConsigneeOut,
    ConsigneeListResponse,
    ConsigneeUpdate,
    OrderCreate,
    OrderOut,
    OrderListResponse,
    BulkOrderListResponse,
    BulkOrderResponse,
    LocationRequest,
    OrderStatusListResponse,
    OrderUpdate,
    

)
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.consigeeauth import AuthUser
from app.utils.webconfig import check_maintenance_mode
from app.services.order_service import (
    search_pickup_addresses,
    create_pickup_address,
    update_pickup_address,
    delete_pickup_address,
    search_consignees,
    create_consignee,
    update_consignee,
    delete_consignee,
    create_order,
    process_bulk_excel_upload,
    list_bulk_orders,
    list_orders,
    get_order,
    get_order_bybarcode,
    get_filtered_orders_service,
    update_order,
    delete_order,
    duplicate_order,
    get_order_counts,
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
# pyzbar imported lazily — see _lazy_decode()
import httpx
from app.models.order import Order, ConsigneeToDelivery, PickupToConsignees,WarehouseToDelivery,FranchiseToDelivery

from datetime import datetime, date
from sqlalchemy import select, func, or_
from enum import Enum 
from app.schemas.order import TodayStatusRequest,OrderStatusRequest 
from app.models.webconfiguration import WebConfiguration

from app.dependencies.consigeeuser import get_current_user as get_current_consigee
from app.models.franchise import OrderFranchiseAddress,Franchise
from app.models.consignee import Consignee
from app.models.pickup_address import PickupAddress
from app.models.franchise import Franchise
from app.models.warehouse import WareHouseAddress

from sqlalchemy import and_, or_, func, select
from sqlalchemy.orm import selectinload, aliased
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional




from typing import Optional, List, Dict, Any
import redis
import hashlib
import base64
import httpx
from app.services.notification_service import create_notification

    
from fastapi.responses import StreamingResponse
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import base64



router = APIRouter(prefix="/orders", tags=["Orders"])


def _lazy_decode(image):
    """Lazy import of pyzbar to avoid crash when DLLs are missing."""
    from pyzbar.pyzbar import decode as _decode
    return _decode(image)


# â”€â”€ Pickup Addresses â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/pickup-addresses", response_model=PickupAddressListResponse)
async def search_pickup_addresses_endpoint(
    search: Optional[str] = Query(None,description="Search by nickname, contact name, address, city, or pincode",),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("pickup_addresses:view")),):
    return await search_pickup_addresses(db=db,current_user=current_user,search=search,page=page,limit=limit,)






@router.post("/pickup-addresses", response_model=PickupAddressOut, status_code=201)
async def create_pickup_address_endpoint(
    data: PickupAddressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    config: WebConfiguration = Depends(check_maintenance_mode),
    _: User = Depends(require_permission("pickup_addresses:create")),
):
    return await create_pickup_address(db, data, current_user)


@router.put("/pickup-addresses/{address_id}", response_model=PickupAddressOut)
async def update_pickup_address_endpoint(
    address_id: str,
    data: PickupAddressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("pickup_addresses:create")),
):
    return await update_pickup_address(db, address_id, data, current_user)


@router.delete("/pickup-addresses/{address_id}", status_code=204)
async def delete_pickup_address_endpoint(
    address_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("pickup_addresses:create")),
):
    await delete_pickup_address(db, address_id, current_user)
    return Response(status_code=204)


# â”€â”€ Consignees â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/consignees", response_model=ConsigneeListResponse)
async def search_consignees_endpoint(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, email, or mobile"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:view")),
):
    return await search_consignees(db, current_user, search=search, page=page, limit=limit)


@router.post("/consignees", response_model=ConsigneeOut, status_code=201)
async def create_consignee_endpoint(
    data: ConsigneeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:create")),
):
    return await create_consignee(db, data, current_user)


@router.put("/consignees/{consignee_id}", response_model=ConsigneeOut)
async def update_consignee_endpoint(
    consignee_id: str,
    data: ConsigneeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:create")),
):
    return await update_consignee(db, consignee_id, data, current_user)


@router.delete("/consignees/{consignee_id}", status_code=204)
async def delete_consignee_endpoint(
    consignee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("consignees:create")),
):
    await delete_consignee(db, consignee_id, current_user)
    return Response(status_code=204)


# â”€â”€ Orders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
    order_type: str = Form(...),
    pickup_address_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:create")),):
    
    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Only Excel and CSV files are supported.")
    
    file_content = await file.read()
    return await process_bulk_excel_upload(
        db=db,
        file_content=file_content,
        file_name=file.filename,
        order_type=order_type,
        pickup_address_id=pickup_address_id,
        current_user=current_user
    )

@router.get("/bulk", response_model=BulkOrderListResponse)
async def list_bulk_orders_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return await list_bulk_orders(db, current_user, page=page, limit=limit)


# @router.get("", response_model=OrderListResponse)
# async def list_orders_endpoint(
#     page: int = Query(1, ge=1),
#     limit: int = Query(10, ge=1, le=100),
#     search: Optional[str] = Query(None, description="Search by order number"),
#     status: Optional[str] = Query(None, description="Filter by status"),
#     order_type: Optional[str] = Query(None, description="Filter by order type (B2C, B2B, International)"),
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
#     _: User = Depends(require_permission("orders:view")),
# ):
#     return await list_orders(
#         db, current_user, page=page, limit=limit,
#         search=search, status_filter=status, order_type=order_type,
#     )

@router.get("")
async def get_orders(
    page: int = Query(1),
    limit: int = Query(10),

    start_date: datetime | None = None,
    end_date: datetime | None = None,

    order_id: str | None = None,
    awb_no: str | None = None,
    buyer_name: str | None = None,

    payment_method: str | None = None,
    status_filter: str | None = None,
    config: WebConfiguration = Depends(check_maintenance_mode),
    bulk_order_id: str | None = Query(None, description="Filter by bulk order ID"),

    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # result = await db.execute(select(WebConfiguration))
    # config = result.scalars().first()
    # if config and config.maintenance_mode:        
    #         raise HTTPException(status_code=503,detail="System under maintenance")

    return await list_orders(
        db=db,
        current_user=current_user,

        page=page,
        limit=limit,

        start_date=start_date,
        end_date=end_date,

        order_id=order_id,
        awb_no=awb_no,
        buyer_name=buyer_name,

        payment_method=payment_method,
        status_filter=status_filter,
        bulk_order_id=bulk_order_id,
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
# pyzbar imported lazily — see _lazy_decode()

import barcode
from barcode.writer import ImageWriter


# 1. Generate 8-char unique public ID
def generate_public_id():
    return str(uuid.uuid4()).replace("-", "")[:8].upper()


# 2. Decode EXISTING barcode image -> get original value
def decode_barcode_from_base64(barcode_base64: str) -> str:
    image_data = base64.b64decode(barcode_base64)
    image = Image.open(BytesIO(image_data))

    decoded_objects = _lazy_decode(image)
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



# @router.put("/{order_id}", response_model=OrderOut)
# async def edit_order(
#     order_id: str,
#     data: OrderUpdate,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     return await update_order(
#         db=db,
#         order_id=order_id,
#         data=data,
#         current_user=current_user,
#     )


@router.delete("/{order_id}/")
async def remove_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return await delete_order(
        db=db,
        order_id=order_id,
        current_user=current_user,
    )


@router.patch("/{order_id}/", response_model=OrderOut)
async def edit_order(
    order_id: str,
    data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return await update_order(
        db=db,
        order_id=order_id,
        data=data,
        current_user=current_user,
    )


@router.post("/{order_id}/duplicate", response_model=OrderOut)
async def duplicate_existing_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = await duplicate_order(db, order_id, current_user)
    await db.commit()
    return order


@router.get("/{order_id}/", response_model=OrderOut)
async def get_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return await get_order(db, order_id, current_user)



@router.get("/getsinglorderbybarcode/{barcode}/",response_model=OrderOut)
async def get_order_endpoint(
    barcode: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_consigee)):
    return await get_order_bybarcode(db,barcode,current_user)



PENDING = "pending"
DISPATCHED = "dispatched"
DELIVERED = "delivered"
CANCELLED = "cancelled"


@router.get("/scan/{barcode}")
async def scan_order(
    barcode: str,
    db: AsyncSession = Depends(get_db),   # ðŸ‘ˆ IMPORTANT (AsyncSession)
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

                decoded = _lazy_decode(img)

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
    
    








# async def resolve_scan_target(db: AsyncSession, code: str):
#     order_stmt = await db.execute(
#         select(Order)
#         .options(
#             selectinload(Order.pickup_address),
#             selectinload(Order.consignee),
#             selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
#             selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
#         )
#         .where(Order.order_number == code))
#     order = order_stmt.scalar_one_or_none()
#     if order:
#         return {"type": "order", "data": order}
#     bag_stmt = await db.execute(
#         select(Bag)
#         .options(selectinload(Bag.bag_orders).selectinload(BagOrder.order))
#         .where(Bag.bag_number == code))
    
#     bag = bag_stmt.scalar_one_or_none()
#     if bag:
#         return {"type": "bag", "data": bag}
#     return None








# from sqlalchemy import select
# from datetime import datetime
# from sqlalchemy.orm import selectinload
# from app.services.notification_service import create_notification

# async def get_pincode_from_lat_lng(lat: float, lng: float):
#     try:
#         url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers={"User-Agent": "courier-app"})
#         if response.status_code == 200:
#             data = response.json()
#             address = data.get("address", {})
#             return {
#                 "pincode": address.get("postcode"),
#                 "city": address.get("city") or address.get("town") or address.get("village"),
#                 "state": address.get("state"),
#                 "country": address.get("country"),
#             }
#         return None
#     except Exception as e:
#         print(f"Geocoding error: {str(e)}")
#         return None

# def build_order_franchisestatus(franchise_mappings, franchise_index: int) -> str:
#     base_status = OrderStatus.DISPATCHED.value
#     if len(franchise_mappings) == 1:
#         return base_status
#     return f"{base_status}_{franchise_index}"


# def build_order_warehousestatus(warehouse_mappings, warehouse_index: int) -> str:
#     base_status = OrderStatus.WAREHOUSE.value
#     if len(warehouse_mappings) == 1:
#         return base_status
#     return f"{base_status}_{warehouse_index}"









# @router.post("/get-pincode/{barcode}")
# async def get_pincode_from_gps(
#     barcode: str,
#     location: LocationRequest,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),):
#     decoded_barcode = barcode.strip()
#     try:
#         decoded_barcode = base64.b64decode(decoded_barcode).decode("utf-8")
#     except Exception:
#         pass
    
    
    
#         # find bag
#     result = await db.execute(
#         select(Bag)
#         .options(
#             selectinload(Bag.bag_orders)
#             .selectinload(BagOrder.order)
#             .selectinload(Order.pickup_address),
#             selectinload(Bag.bag_orders)
#             .selectinload(BagOrder.order)
#             .selectinload(Order.consignee),
#             selectinload(Bag.bag_orders)
#             .selectinload(BagOrder.order)
#             .selectinload(Order.warehouse_addresses)
#             .selectinload(OrderWarehouseAddress.warehouse_address),
#             selectinload(Bag.bag_orders)
#             .selectinload(BagOrder.order)
#             .selectinload(Order.franchise_addresses)
#             .selectinload(OrderFranchiseAddress.franchise_address),
#         )
#         .where(Bag.bag_number == decoded_barcode)
#     )

#     bag = result.scalar_one_or_none()

#     if not bag:
#         raise HTTPException(404, "Bag not found")
    
    
    
#     gps_data = await get_pincode_from_lat_lng(location.lat, location.lng)
#     if not gps_data or not gps_data.get("pincode"):
#         raise HTTPException(status_code=400, detail="Could not determine pincode")
#     gps_pincode = str(gps_data["pincode"]).strip()
#     gps_pincode = gps_pincode.replace(".0", "")
#     gps_pincode = "".join(filter(str.isdigit, gps_pincode))
    
#     scan_target = await resolve_scan_target(db, decoded_barcode)

#     if not scan_target:
#         raise HTTPException(404, "Barcode not found")
    
    
#     if scan_target["type"] == "bag":

#         responses = []

#         for bag_order in bag.bag_orders:
#             order = bag_order.order

#             if not order:
#                 continue

#             pickup = order.pickup_address
#             consignee = order.consignee
#             warehouse_mappings = order.warehouse_addresses
#             franchise_mappings = order.franchise_addresses

#             try:

#                 # ======================
#                 # PICKUP CHECK
#                 # ======================
#                 if pickup and str(pickup.pincode).strip() == gps_pincode:

#                     existing = await db.execute(
#                         select(PickupToConsignees).where(
#                             PickupToConsignees.order_id == order.id
#                         )
#                     )

#                     if not existing.scalar_one_or_none():

#                         db.add(PickupToConsignees(
#                             pincode=pickup.pincode,
#                             status=OrderStatus.PICKED,
#                             order_id=order.id,
#                             pickup_addresses_id=pickup.id,
#                             user_id=current_user.id
#                         ))

#                         order.previous_status = order.status
#                         order.status = OrderStatus.PICKED

#                 # ======================
#                 # WAREHOUSE CHECK
#                 # ======================
#                 for i, m in enumerate(warehouse_mappings, start=1):
#                     wh = m.warehouse_address

#                     if wh and str(wh.pincode).strip() == gps_pincode:

#                         existing = await db.execute(
#                             select(WarehouseToDelivery).where(
#                                 WarehouseToDelivery.order_id == order.id,
#                                 WarehouseToDelivery.pincode == gps_pincode
#                             )
#                         )

#                         if not existing.scalar_one_or_none():

#                             status = build_order_warehousestatus(warehouse_mappings, i)

#                             db.add(WarehouseToDelivery(
#                                 pincode=wh.pincode,
#                                 status=status,
#                                 order_id=order.id,
#                                 warehouse_addresses_id=wh.id,
#                                 user_id=current_user.id
#                             ))

#                             order.previous_status = order.status
#                             order.status = status

#                 # ======================
#                 # FRANCHISE CHECK
#                 # ======================
#                 for i, m in enumerate(franchise_mappings, start=1):
#                     fr = m.franchise_address

#                     if fr and str(fr.pincode).strip() == gps_pincode:

#                         existing = await db.execute(
#                             select(FranchiseToDelivery).where(
#                                 FranchiseToDelivery.order_id == order.id,
#                                 FranchiseToDelivery.pincode == gps_pincode
#                             )
#                         )

#                         if not existing.scalar_one_or_none():

#                             status = build_order_franchisestatus(franchise_mappings, i)

#                             db.add(FranchiseToDelivery(
#                                 pincode=fr.pincode,
#                                 status=status,
#                                 order_id=order.id,
#                                 franchise_addresses_id=fr.id,
#                                 user_id=current_user.id
#                             ))

#                             order.previous_status = order.status
#                             order.status = status

#                 # ======================
#                 # DELIVERY CHECK
#                 # ======================
#                 if consignee and str(consignee.pincode).strip() == gps_pincode:

#                     existing = await db.execute(
#                         select(ConsigneeToDelivery).where(
#                             ConsigneeToDelivery.order_id == order.id
#                         )
#                     )

#                     if not existing.scalar_one_or_none():

#                         db.add(ConsigneeToDelivery(
#                             pincode=consignee.pincode,
#                             status=OrderStatus.DELIVERED,
#                             order_id=order.id,
#                             consignee_id=consignee.id,
#                             user_id=current_user.id
#                         ))

#                         order.previous_status = order.status
#                         order.status = OrderStatus.DELIVERED

#                 responses.append({
#                     "order_id": order.id,
#                     "order_number": order.order_number,
#                     "status": order.status
#                 })

#             except Exception as e:
#                 responses.append({
#                     "order_id": order.id,
#                     "error": str(e)
#                 })

#         await db.commit()

#         return {
#             "bag_id": bag.id,
#             "bag_number": bag.bag_number,
#             "processed_orders": len(bag.bag_orders),
#             "results": responses
#         }
        
        
    
    
#     if scan_target["type"] == "order": 
#         print('gps_pincode',gps_pincode)
#         stmt = (
#             select(Order)
#             .options(
#                 selectinload(Order.pickup_address),
#                 selectinload(Order.consignee),
#                 selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
#                 selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
#             )
#             .where(Order.order_number == decoded_barcode))
#         result = await db.execute(stmt)
#         order = result.scalar_one_or_none()
#         if not order:
#             raise HTTPException(status_code=404, detail="Order not found")
#         pickup = order.pickup_address
#         consignee = order.consignee
#         warehouse_mappings = order.warehouse_addresses
#         franchise_mappings = order.franchise_addresses
#         existing = await db.execute(select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order.id))
#         if existing.scalar_one_or_none():
#             raise HTTPException(status_code=409, detail="Already delivered") 
#         if not pickup:
#             raise HTTPException(status_code=404, detail="Pickup not found")
#         if not consignee:
#             raise HTTPException(status_code=404, detail="Consignee not found")
        
#         print("gps_pincode gps_pincode  ",gps_pincode)
#         pickup_pincode = str(pickup.pincode).strip()
#         if pickup_pincode == gps_pincode:
#             existing = await db.execute(select(PickupToConsignees).where(PickupToConsignees.order_id == order.id))
#             if existing.scalar_one_or_none():
#                 raise HTTPException(status_code=409, detail="Pickup already done")
#             entry = PickupToConsignees(pincode=pickup.pincode,status=OrderStatus.PICKED,order_id=order.id,pickup_addresses_id=pickup.id,user_id=current_user.id)
#             db.add(entry)
#             order.previous_status=order.status
#             order.status = OrderStatus.PICKED
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Order Picked",message=f"Order {order.order_number} picked",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(entry)
#             return {
#                 "stage": "Picked",
#                 "order_id": order.id,
#                 "user_id": current_user.id,
#                 "order_number": order.order_number,
#                 "order_status": order.status,
#                 "record_id": entry.id,
#                 "pickup_address_id": pickup.id,
#                 "pincode": pickup.pincode,
#                 "city": pickup.city,
#                 "state": pickup.state,
#                 "address": pickup.address_line_1,
#                 "contact_name": pickup.contact_name,
#                 "phone": pickup.phone,
#                 "gps_pincode": gps_pincode,
#             }
            
#         matched_warehouse = None
#         warehouse_index = 0
#         for i, mapping in enumerate(warehouse_mappings, start=1):
#             wh = mapping.warehouse_address
#             if wh and str(wh.pincode).strip() == gps_pincode:    
#                 matched_warehouse = wh
#                 warehouse_index = i
#                 break

#         if matched_warehouse:
#             existing = await db.execute(select(WarehouseToDelivery).where(WarehouseToDelivery.pincode ==gps_pincode,WarehouseToDelivery.order_id == order.id))
#             # if existing.scalar_one_or_none():
#             existing_data = existing.scalars().first()
#             if existing_data:    
#                 raise HTTPException(status_code=409, detail="Warehouse already done")
#             status = build_order_warehousestatus(warehouse_mappings, warehouse_index)
#             entry = WarehouseToDelivery(pincode=matched_warehouse.pincode,status=status,order_id=order.id,warehouse_addresses_id=matched_warehouse.id,user_id=current_user.id)
#             db.add(entry)
#             order.previous_status=order.status
#             order.status = status
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Order WAREHOUSE",message=f"Order {order.order_number} {status} successfully",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(entry)
#             return {
#             "stage": status,
#             "order_id": order.id,
#             "user_id": current_user.id,
#             "order_number": order.order_number,
#             "order_status": order.status,
#             "record_id": entry.id,
#             "warehouse_address_id": matched_warehouse.id,
#             "pincode": matched_warehouse.pincode,
#             "city": matched_warehouse.city,
#             "state": matched_warehouse.state,
#             "address": matched_warehouse.address_line_1,
#             "contact_name": matched_warehouse.contact_name,
#             "phone": matched_warehouse.phone,
#             "gps_pincode": gps_pincode,
#             }

#         matched_franchise = None
#         franchise_index = 0
#         for i, mapping in enumerate(franchise_mappings, start=1):
#             fr = mapping.franchise_address   
#             print('fr.pincode   ',fr.pincode)
#             if fr and str(fr.pincode).strip() == gps_pincode:   
#                 matched_franchise = fr
#                 franchise_index = i
                
#                 break
#         print('matched_franchise  ',matched_franchise)    
#         if matched_franchise:
#             existing = await db.execute(select(FranchiseToDelivery).where(FranchiseToDelivery.pincode == gps_pincode,FranchiseToDelivery.order_id == order.id))
#             existing_data = existing.scalars().first()
#             if existing_data:    
#                 raise HTTPException(status_code=409, detail="Franchise already done")
#             status = build_order_franchisestatus(franchise_mappings, franchise_index)
#             entry = FranchiseToDelivery(pincode=matched_franchise.pincode,status=status,order_id=order.id,franchise_addresses_id=matched_franchise.id,user_id=current_user.id)
#             db.add(entry)
#             order.previous_status=order.status
#             order.status = status
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Order DISPATCHED",message=f"Order {order.order_number} {status} successfully",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(entry)
#             return {
#             "stage": status,
#             "order_id": order.id,
#             "user_id": current_user.id,
#             "order_number": order.order_number,
#             "order_status": order.status,
#             "record_id": entry.id,
#             "franchise_address_id": matched_franchise.id,
#             "pincode": matched_franchise.pincode,
#             "address": matched_franchise.address,
#             "gender": matched_franchise.gender,
#             "current_address": matched_franchise.current_address,
#             "name": matched_franchise.name,
#             "phone": matched_franchise.phone,
#             "gps_pincode": gps_pincode,
#             }
                

#         consignee_pincode = str(consignee.pincode).strip()
#         if consignee_pincode == gps_pincode:  
#             print("consignee.pincode == gps_pincode",consignee.pincode,"   ",gps_pincode)  
#             existing = await db.execute(select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order.id))
#             if existing.scalar_one_or_none():
#                 raise HTTPException(status_code=409, detail="Already delivered")
#             entry = ConsigneeToDelivery(pincode=consignee.pincode,status=OrderStatus.DELIVERED,order_id=order.id,consignee_id=consignee.id,user_id=current_user.id)
#             db.add(entry)
#             order.previous_status=order.status
#             order.status = OrderStatus.DELIVERED
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Order Delivered",message=f"Order {order.order_number} Delivered successfully",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(entry)
#             return {
#                 "stage": "Delivered",
#                 "order_id": order.id,
#                 "user_id": current_user.id,
#                 "order_number": order.order_number,
#                 "order_status": order.status,
#                 "record_id": entry.id,
#                 "consignee_id": consignee.id,
#                 "pincode": consignee.pincode,
#                 "consignee_name": consignee.name,
#                 "consignee_phone": consignee.mobile,
#                 "consignee_address": consignee.address_line_1,
#                 "consignee_city": consignee.city,
#                 "consignee_state": consignee.state,
#                 "gps_pincode": gps_pincode,
#             }
            
            
            
#         warehouse_stmt = await db.execute(select(WareHouseAddress).where(func.replace(func.trim(WareHouseAddress.pincode), ' ', '') == gps_pincode))
#         global_warehouse = warehouse_stmt.scalar_one_or_none()
#         if global_warehouse:
#             existing_mapping_stmt = await db.execute(
#                 select(OrderWarehouseAddress).where(
#                     OrderWarehouseAddress.order_id == order.id,
#                     OrderWarehouseAddress.warehouse_address_id == global_warehouse.id))
            
#             existing_mapping = existing_mapping_stmt.scalar_one_or_none()
#             existing = await db.execute(select(WarehouseToDelivery).where(WarehouseToDelivery.order_id == order.id,WarehouseToDelivery.pincode == gps_pincode))
#             existing_data = existing.scalars().first()
#             if existing_data:
#                 raise HTTPException(status_code=409, detail="Warehouse already done")
#             if not existing_mapping:
#                 new_mapping = OrderWarehouseAddress(order_id=order.id,warehouse_address_id=global_warehouse.id)
#                 db.add(new_mapping)
#                 await db.flush()
#                 warehouse_mappings.append(new_mapping)
#             warehouse_index = len(warehouse_mappings)
#             status = build_order_warehousestatus(warehouse_mappings,warehouse_index)
#             tracking = WarehouseToDelivery(
#                 pincode=global_warehouse.pincode,
#                 status=status,
#                 order_id=order.id,
#                 warehouse_addresses_id=global_warehouse.id,
#                 user_id=current_user.id)
#             db.add(tracking)
#             order.previous_status=order.status
#             order.status = status
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Warehouse Scan",message=f"Order {order.order_number} reached warehouse",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(tracking)

#             return {
#                 "stage": status,
#                 "type": "warehouse",
#                 "order_id": order.id,
#                 "order_number": order.order_number,
#                 "warehouse_id": global_warehouse.id,
#                 "warehouse_name": global_warehouse.nickname,
#                 "pincode": global_warehouse.pincode,
#                 "city": global_warehouse.city,
#                 "state": global_warehouse.state,
#                 "gps_pincode": gps_pincode,
#             }
        
        
        
        
        
#         franchise_stmt = await db.execute(select(Franchise).where(func.replace(func.trim(Franchise.pincode), ' ', '') == gps_pincode))
#         global_franchise = franchise_stmt.scalar_one_or_none()
#         if global_franchise:
#             existing_mapping_stmt = await db.execute(
#                 select(OrderFranchiseAddress).where(
#                     OrderFranchiseAddress.order_id == order.id,
#                     OrderFranchiseAddress.franchise_address_id == global_franchise.id))
#             existing_mapping = existing_mapping_stmt.scalar_one_or_none()
#             existing = await db.execute(select(FranchiseToDelivery).where(FranchiseToDelivery.pincode == gps_pincode,FranchiseToDelivery.order_id == order.id))
#             existing_data = existing.scalars().first()
#             if existing_data:
#                 raise HTTPException(status_code=409, detail="Franchise already done")
#             if not existing_mapping:
#                 new_mapping = OrderFranchiseAddress(order_id=order.id,franchise_address_id=global_franchise.id)
#                 db.add(new_mapping)
#                 await db.flush()
#                 franchise_mappings.append(new_mapping)
#             franchise_index = len(franchise_mappings)
#             status = build_order_franchisestatus(franchise_mappings,franchise_index)
#             tracking = FranchiseToDelivery(
#                 pincode=global_franchise.pincode,
#                 status=status,
#                 order_id=order.id,
#                 franchise_addresses_id=global_franchise.id,
#                 user_id=current_user.id
#             )
#             db.add(tracking)
#             order.previous_status=order.status
#             order.status = status
#             order.updated_at = datetime.now(IST)
#             await create_notification(db=db,title="Franchise Scan",message=f"Order {order.order_number} reached franchise",type="order",order_id=order.id,)
#             await db.commit()
#             await db.refresh(tracking)
#             return {
#                 "stage": status,
#                 "type": "franchise",
#                 "order_id": order.id,
#                 "order_number": order.order_number,
#                 "franchise_id": global_franchise.id,
#                 "franchise_name": global_franchise.name,
#                 "pincode": global_franchise.pincode,
#                 "gps_pincode": gps_pincode,
#             }
#         raise HTTPException(status_code=400,detail="GPS does not match pickup, warehouse, franchise, or delivery")








from app.services.notification_service import create_notification
from app.models.order import indian_time
redis_client = None

def get_redis_client():
    global redis_client
    if not redis_client:
        redis_client = redis.Redis(host='localhost',port=6379,decode_responses=True,socket_connect_timeout=2)
    return redis_client


# ============= HELPER FUNCTIONS =============

async def get_pincode_from_lat_lng(lat: float, lng: float):
    """Get pincode from GPS coordinates"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"User-Agent": "courier-app"})
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            pincode = address.get("postcode")
            if pincode:
                pincode = str(pincode).replace(".0", "").strip()
                pincode = "".join(filter(str.isdigit, pincode))
            return {
                "pincode": pincode,
                "city": address.get("city") or address.get("town") or address.get("village"),
                "state": address.get("state"),
                "country": address.get("country"),
            }
        return None
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return None


def build_order_warehousestatus(warehouse_count: int, warehouse_index: int) -> str:
    """Build warehouse status with index if multiple warehouses"""
    base_status = OrderStatus.WAREHOUSE.value
    if warehouse_count <= 1:
        return base_status
    return f"{base_status}_{warehouse_index}"


def build_order_franchisestatus(franchise_count: int, franchise_index: int) -> str:
    """Build franchise status with index if multiple franchises"""
    base_status = OrderStatus.DISPATCHED.value
    if franchise_count <= 1:
        return base_status
    return f"{base_status}_{franchise_index}"


async def get_or_create_idempotency_key(db: AsyncSession, barcode: str, gps_pincode: str) -> bool:
    """Check if this scan was already processed (idempotency protection)"""
    redis_client = get_redis_client()
    scan_key = f"scan:{hashlib.md5(f"{barcode}:{gps_pincode}".encode()).hexdigest()}"
    
    # Check if already processed
    if redis_client.exists(scan_key):
        return False
    
    # Store with 5 minute expiry
    redis_client.setex(scan_key, 300, "processing")
    return True


async def resolve_scan_target(db: AsyncSession, code: str):
    """Resolve barcode to either Order or Bag with optimized loading"""
    # Check for Order
    order_stmt = await db.execute(
        select(Order)
        .options(
            selectinload(Order.pickup_address),
            selectinload(Order.consignee),
            selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
            selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
        )
        .where(Order.order_number == code)
    )
    order = order_stmt.scalar_one_or_none()
    if order:
        return {"type": "order", "data": order}
    
    # Check for Bag with optimized loading
    bag_stmt = await db.execute(
        select(Bag)
        .options(
            selectinload(Bag.bag_orders).selectinload(BagOrder.order).selectinload(Order.items),
            selectinload(Bag.bag_orders).selectinload(BagOrder.order).selectinload(Order.pickup_address),
            selectinload(Bag.bag_orders).selectinload(BagOrder.order).selectinload(Order.consignee),
            selectinload(Bag.bag_orders).selectinload(BagOrder.order).selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
            selectinload(Bag.bag_orders).selectinload(BagOrder.order).selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
        )
        .where(Bag.bag_number == code)
    )
    bag = bag_stmt.scalar_one_or_none()
    if bag:
        return {"type": "bag", "data": bag}
    
    return None


async def preload_tracking_statuses(db: AsyncSession, order_ids: List[str]) -> Dict[str, Dict]:
    """Batch preload tracking statuses to avoid N+1 queries"""
    # Batch load all tracking data
    pickup_data = await db.execute(
        select(PickupToConsignees).where(PickupToConsignees.order_id.in_(order_ids))
    )
    warehouse_data = await db.execute(
        select(WarehouseToDelivery).where(WarehouseToDelivery.order_id.in_(order_ids))
    )
    franchise_data = await db.execute(
        select(FranchiseToDelivery).where(FranchiseToDelivery.order_id.in_(order_ids))
    )
    delivery_data = await db.execute(
        select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id.in_(order_ids))
    )
    
    # Organize by order_id
    tracking_map = {order_id: {
        "pickup_exists": False,
        "warehouse_pincodes": set(),
        "franchise_pincodes": set(),
        "delivered": False
    } for order_id in order_ids}
    
    for p in pickup_data.scalars().all():
        if p.order_id in tracking_map:
            tracking_map[p.order_id]["pickup_exists"] = True
    
    for w in warehouse_data.scalars().all():
        if w.order_id in tracking_map:
            tracking_map[w.order_id]["warehouse_pincodes"].add(w.pincode)
    
    for f in franchise_data.scalars().all():
        if f.order_id in tracking_map:
            tracking_map[f.order_id]["franchise_pincodes"].add(f.pincode)
    
    for d in delivery_data.scalars().all():
        if d.order_id in tracking_map:
            tracking_map[d.order_id]["delivered"] = True
    
    return tracking_map


# ============= SINGLE ORDER SCAN PROCESSING =============

async def process_order_scan(
    db: AsyncSession, 
    order: Order, 
    gps_pincode: str, 
    current_user: User,
    tracking_cache: Dict = None
):
    """Process single order scan with optimized DB access"""
    
    pickup = order.pickup_address
    consignee = order.consignee
    
    # Get warehouse and franchise mappings
    warehouse_mappings = order.warehouse_addresses or []
    franchise_mappings = order.franchise_addresses or []
    
    # Use cache if provided, otherwise query
    if tracking_cache:
        order_tracking = tracking_cache.get(order.id, {})
        if order_tracking.get("delivered"):
            raise HTTPException(status_code=409, detail="Order already delivered")
    else:
        # Fallback to direct query
        delivered_check = await db.execute(
            select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order.id)
        )
        if delivered_check.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Order already delivered")
    
    # 1. Check Pickup
    if pickup and str(pickup.pincode).strip() == gps_pincode:
        # Check if already picked using cache or query
        if tracking_cache and tracking_cache.get(order.id, {}).get("pickup_exists"):
            raise HTTPException(status_code=409, detail="Pickup already done")
        elif not tracking_cache:
            existing = await db.execute(
                select(PickupToConsignees).where(PickupToConsignees.order_id == order.id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Pickup already done")
        
        entry = PickupToConsignees(
            pincode=pickup.pincode,
            status=OrderStatus.PICKED.value,
            order_id=order.id,
            pickup_addresses_id=pickup.id,
            user_id=current_user.id
        )
        db.add(entry)
        order.previous_status = order.status
        order.status = OrderStatus.PICKED.value
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Order Picked",
            message=f"Order {order.order_number} picked successfully",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": "Picked",
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": entry.id,
            "pickup_address_id": pickup.id,
            "pincode": pickup.pincode,
            "city": pickup.city,
            "state": pickup.state,
            "address": pickup.address_line_1,
            "contact_name": pickup.contact_name,
            "phone": pickup.phone,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    # 2. Check Warehouse (exact match)
    matched_warehouse = None
    warehouse_index = 0
    for i, mapping in enumerate(warehouse_mappings, start=1):
        wh = mapping.warehouse_address
        if wh and str(wh.pincode).strip() == gps_pincode:
            matched_warehouse = wh
            warehouse_index = i
            break
    
    if matched_warehouse:
        # Check if already processed at this warehouse
        if tracking_cache and gps_pincode in tracking_cache.get(order.id, {}).get("warehouse_pincodes", set()):
            raise HTTPException(status_code=409, detail="Warehouse already processed")
        elif not tracking_cache:
            existing = await db.execute(
                select(WarehouseToDelivery).where(
                    WarehouseToDelivery.order_id == order.id,
                    WarehouseToDelivery.pincode == gps_pincode
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Warehouse already processed")
        
        status = build_order_warehousestatus(len(warehouse_mappings), warehouse_index)
        entry = WarehouseToDelivery(
            pincode=matched_warehouse.pincode,
            status=status,
            order_id=order.id,
            warehouse_addresses_id=matched_warehouse.id,
            user_id=current_user.id
        )
        db.add(entry)
        order.previous_status = order.status
        order.status = status
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Order at Warehouse",
            message=f"Order {order.order_number} reached warehouse ({status})",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": status,
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": entry.id,
            "warehouse_address_id": matched_warehouse.id,
            "pincode": matched_warehouse.pincode,
            "city": matched_warehouse.city,
            "state": matched_warehouse.state,
            "address": matched_warehouse.address_line_1,
            "contact_name": matched_warehouse.contact_name,
            "phone": matched_warehouse.phone,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    # 3. Check Franchise (exact match)
    matched_franchise = None
    franchise_index = 0
    for i, mapping in enumerate(franchise_mappings, start=1):
        fr = mapping.franchise_address
        if fr and str(fr.pincode).strip() == gps_pincode:
            matched_franchise = fr
            franchise_index = i
            break
    
    if matched_franchise:
        if tracking_cache and gps_pincode in tracking_cache.get(order.id, {}).get("franchise_pincodes", set()):
            raise HTTPException(status_code=409, detail="Franchise already processed")
        elif not tracking_cache:
            existing = await db.execute(
                select(FranchiseToDelivery).where(
                    FranchiseToDelivery.order_id == order.id,
                    FranchiseToDelivery.pincode == gps_pincode
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Franchise already processed")
        
        status = build_order_franchisestatus(len(franchise_mappings), franchise_index)
        entry = FranchiseToDelivery(
            pincode=matched_franchise.pincode,
            status=status,
            order_id=order.id,
            franchise_addresses_id=matched_franchise.id,
            user_id=current_user.id
        )
        db.add(entry)
        order.previous_status = order.status
        order.status = status
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Order at Franchise",
            message=f"Order {order.order_number} reached franchise ({status})",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": status,
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": entry.id,
            "franchise_address_id": matched_franchise.id,
            "name": matched_franchise.name,
            "phone": matched_franchise.phone,
            "pincode": matched_franchise.pincode,
            "address": matched_franchise.address,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    # 4. Check Delivery
    if consignee and str(consignee.pincode).strip() == gps_pincode:
        if tracking_cache and tracking_cache.get(order.id, {}).get("delivered"):
            raise HTTPException(status_code=409, detail="Already delivered")
        elif not tracking_cache:
            existing = await db.execute(
                select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order.id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Already delivered")
        
        entry = ConsigneeToDelivery(
            pincode=consignee.pincode,
            status=OrderStatus.DELIVERED.value,
            order_id=order.id,
            consignee_id=consignee.id,
            user_id=current_user.id
        )
        db.add(entry)
        order.previous_status = order.status
        order.status = OrderStatus.DELIVERED.value
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Order Delivered",
            message=f"Order {order.order_number} delivered successfully",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": "Delivered",
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "record_id": entry.id,
            "consignee_id": consignee.id,
            "pincode": consignee.pincode,
            "consignee_name": consignee.name,
            "consignee_phone": consignee.mobile,
            "consignee_address": consignee.address_line_1,
            "consignee_city": consignee.city,
            "consignee_state": consignee.state,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    # 5. Try global warehouse match
    warehouse_stmt = await db.execute(
        select(WareHouseAddress).where(
            func.replace(func.trim(WareHouseAddress.pincode), ' ', '') == gps_pincode
        )
    )
    global_warehouse = warehouse_stmt.scalar_one_or_none()
    
    if global_warehouse:
        # Check if already mapped
        existing_mapping_stmt = await db.execute(
            select(OrderWarehouseAddress).where(
                OrderWarehouseAddress.order_id == order.id,
                OrderWarehouseAddress.warehouse_address_id == global_warehouse.id
            )
        )
        existing_mapping = existing_mapping_stmt.scalar_one_or_none()
        
        # Check if already processed (using cache if available)
        if tracking_cache and gps_pincode in tracking_cache.get(order.id, {}).get("warehouse_pincodes", set()):
            raise HTTPException(status_code=409, detail="Warehouse already processed")
        elif not tracking_cache:
            existing_tracking = await db.execute(
                select(WarehouseToDelivery).where(
                    WarehouseToDelivery.order_id == order.id,
                    WarehouseToDelivery.pincode == gps_pincode
                )
            )
            if existing_tracking.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Warehouse already processed")
        
        # Add mapping if not exists
        if not existing_mapping:
            new_mapping = OrderWarehouseAddress(
                order_id=order.id,
                warehouse_address_id=global_warehouse.id
            )
            db.add(new_mapping)
            await db.flush()
        
        # Get current count from DB, not from memory
        current_count_stmt = await db.execute(
            select(func.count(OrderWarehouseAddress.id))
            .where(OrderWarehouseAddress.order_id == order.id)
        )
        warehouse_count = current_count_stmt.scalar() or 1
        
        status = build_order_warehousestatus(warehouse_count, warehouse_count)
        
        tracking = WarehouseToDelivery(
            pincode=global_warehouse.pincode,
            status=status,
            order_id=order.id,
            warehouse_addresses_id=global_warehouse.id,
            user_id=current_user.id
        )
        db.add(tracking)
        order.previous_status = order.status
        order.status = status
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Warehouse Scan",
            message=f"Order {order.order_number} reached warehouse",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": status,
            "type": "warehouse",
            "order_id": order.id,
            "order_number": order.order_number,
            "warehouse_id": global_warehouse.id,
            "warehouse_name": global_warehouse.nickname,
            "pincode": global_warehouse.pincode,
            "city": global_warehouse.city,
            "state": global_warehouse.state,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    # 6. Try global franchise match
    franchise_stmt = await db.execute(
        select(Franchise).where(
            func.replace(func.trim(Franchise.pincode), ' ', '') == gps_pincode
        )
    )
    global_franchise = franchise_stmt.scalar_one_or_none()
    
    if global_franchise:
        existing_mapping_stmt = await db.execute(
            select(OrderFranchiseAddress).where(
                OrderFranchiseAddress.order_id == order.id,
                OrderFranchiseAddress.franchise_address_id == global_franchise.id
            )
        )
        existing_mapping = existing_mapping_stmt.scalar_one_or_none()
        
        if tracking_cache and gps_pincode in tracking_cache.get(order.id, {}).get("franchise_pincodes", set()):
            raise HTTPException(status_code=409, detail="Franchise already processed")
        elif not tracking_cache:
            existing_tracking = await db.execute(
                select(FranchiseToDelivery).where(
                    FranchiseToDelivery.order_id == order.id,
                    FranchiseToDelivery.pincode == gps_pincode
                )
            )
            if existing_tracking.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Franchise already processed")
        
        if not existing_mapping:
            new_mapping = OrderFranchiseAddress(
                order_id=order.id,
                franchise_address_id=global_franchise.id
            )
            db.add(new_mapping)
            await db.flush()
        
        current_count_stmt = await db.execute(
            select(func.count(OrderFranchiseAddress.id))
            .where(OrderFranchiseAddress.order_id == order.id)
        )
        franchise_count = current_count_stmt.scalar() or 1
        
        status = build_order_franchisestatus(franchise_count, franchise_count)
        
        tracking = FranchiseToDelivery(
            pincode=global_franchise.pincode,
            status=status,
            order_id=order.id,
            franchise_addresses_id=global_franchise.id,
            user_id=current_user.id
        )
        db.add(tracking)
        order.previous_status = order.status
        order.status = status
        order.updated_at = indian_time()
        
        await create_notification(
            db=db,
            title="Franchise Scan",
            message=f"Order {order.order_number} reached franchise",
            type="order",
            order_id=order.id,
        )
        
        return {
            "stage": status,
            "type": "franchise",
            "order_id": order.id,
            "order_number": order.order_number,
            "franchise_id": global_franchise.id,
            "franchise_name": global_franchise.name,
            "pincode": global_franchise.pincode,
            "gps_pincode": gps_pincode,
            "success": True
        }
    
    raise HTTPException(
        status_code=400,
        detail=f"GPS pincode {gps_pincode} does not match pickup, warehouse, franchise, or delivery location for this order"
    )






async def process_bag_scan(
    db: AsyncSession,
    bag: Bag,
    gps_pincode: str,
    current_user: User
):
    """Process bulk bag scan - NO manual transaction management"""
    responses = []
    successful = 0
    failed = 0
    
    # Define status priority (higher number = more advanced)
    def get_status_priority(status: str) -> int:
        if not status:
            return 0
        if status == "Picked":
            return 10
        elif status and status.startswith("Warehouse"):
            try:
                num = int(status.split("_")[1]) if "_" in status else 1
                return 20 + (num - 1)
            except:
                return 20
        elif status and status.startswith("Dispatched"):
            try:
                num = int(status.split("_")[1]) if "_" in status else 1
                return 30 + (num - 1)
            except:
                return 30
        elif status == "Delivered":
            return 100
        return 0
    
    highest_priority = get_status_priority(bag.status)
    
    # Preload all tracking data for orders in bag
    order_ids = [bo.order.id for bo in bag.bag_orders if bo.order]
    tracking_cache = await preload_tracking_statuses(db, order_ids)
    
    # Process each order - NO begin_nested, NO begin()
    for bag_order in bag.bag_orders:
        order = bag_order.order
        if not order:
            continue
        
        try:
            # Direct call WITHOUT any transaction context
            result = await process_order_scan(db, order, gps_pincode, current_user, tracking_cache)
            await db.refresh(order)
            
            stage = result.get("stage")
            current_priority = get_status_priority(stage)
            
            # Update bag status if this order reached a higher stage
            if current_priority > highest_priority:
                highest_priority = current_priority
                bag.status = stage
                bag.pincode = gps_pincode
                bag.updated_at = indian_time()
                
                # Create bag-level notification (don't await if not needed)
                try:
                    await create_notification(
                        db=db,
                        title=f"Bag {bag.status}",
                        message=f"Bag {bag.bag_number} has been {bag.status} at pincode {gps_pincode}",
                        type="bag",
                        order_id=None,
                        bag_id=bag.id
                    )
                except:
                    pass  # Don't let notification failure break the scan
            
            responses.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "status": stage,
                "success": True,
                "details": result
            })
            successful += 1
            
        except HTTPException as e:
            responses.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "error": e.detail,
                "success": False
            })
            failed += 1
        except Exception as e:
            responses.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "error": str(e),
                "success": False
            })
            failed += 1
    
    # Commit all changes at once
    db.add(bag)
    await db.commit()
    
    return {
        "bag_id": bag.id,
        "bag_number": bag.bag_number,
        "bag_status": bag.status,
        "bag_pincode": bag.pincode,
        "total_orders": len(bag.bag_orders),
        "successful_scans": successful,
        "failed_scans": failed,
        "results": responses
    }










@router.post("/get-pincode/{barcode}", response_model=None)
async def scan_with_location(
    barcode: str,
    location: LocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    lat = location.lat
    lng = location.lng
    
    # Decode barcode if base64 encoded
    decoded_barcode = barcode.strip()
    try:
        decoded_barcode = base64.b64decode(decoded_barcode).decode("utf-8")
    except Exception:
        pass
    
    # Get pincode from GPS
    gps_data = await get_pincode_from_lat_lng(lat, lng)
    if not gps_data or not gps_data.get("pincode"):
        raise HTTPException(status_code=400, detail="Could not determine pincode from GPS coordinates")
    
    gps_pincode = gps_data["pincode"]
    
    # Resolve scan target (order or bag)
    scan_target = await resolve_scan_target(db, decoded_barcode)
    if not scan_target:
        raise HTTPException(status_code=404, detail="Barcode not found for any order or bag")
    
    # NO try-except with rollback - let the session handle it automatically
    if scan_target["type"] == "order":
        result = await process_order_scan(db, scan_target["data"], gps_pincode, current_user)
        await db.commit()
        
        return {
            "scan_type": "order",
            **result,
            "gps_location": {
                "lat": lat,
                "lng": lng,
                "pincode": gps_pincode,
                "city": gps_data.get("city"),
                "state": gps_data.get("state")
            }
        }
    
    elif scan_target["type"] == "bag":
        # Process bag WITHOUT any transaction management here
        result = await process_bag_scan(db, scan_target["data"], gps_pincode, current_user)
        
        # NO commit here - let process_bag_scan handle it
        return {
            "scan_type": "bag",
            **result,
            "gps_location": {
                "lat": lat,
                "lng": lng,
                "pincode": gps_pincode,
                "city": gps_data.get("city"),
                "state": gps_data.get("state")
            }
        }






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
    status: str = Query(...,description="Delivered | Picked | Dispatched | Warehouse | Processing"),
    route_status: Optional[str] = Query(None,description="Dispatched_1 | Dispatched_2 | Warehouse_1 | Warehouse_2"),
    search: Optional[str] = Query(None,description="Search by pincode / consignee / pickup / warehouse / franchise / order number"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),

    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):

    allowed_status = [
        "Delivered",
        "Picked",
        "Dispatched",
        "Warehouse",
        "Processing"
    ]

    if status not in allowed_status:
        raise HTTPException(status_code=400,detail=f"Allowed status: {allowed_status}")
    role_stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == current_user.id))
    role_result = await db.execute(role_stmt)
    role_name = role_result.scalar_one_or_none()

    offset = (page - 1) * limit

    # =========================================================
    # ALIAS
    # =========================================================

    warehouse_alias = aliased(WareHouseAddress)
    franchise_alias = aliased(Franchise)

    # =========================================================
    # BASE QUERY
    # =========================================================

    stmt = (
        select(Order)
        .options(
            selectinload(Order.items),

            selectinload(Order.packages),

            selectinload(Order.consignee),

            selectinload(Order.pickup_address),

            selectinload(Order.warehouse_addresses)
            .selectinload(OrderWarehouseAddress.warehouse_address),

            selectinload(Order.franchise_addresses)
            .selectinload(OrderFranchiseAddress.franchise_address),
        )

        .join(
            Consignee,
            Order.consignee_id == Consignee.id
        )

        .join(
            PickupAddress,
            Order.pickup_address_id == PickupAddress.id
        )

        .outerjoin(
            OrderWarehouseAddress,
            OrderWarehouseAddress.order_id == Order.id
        )

        .outerjoin(
            warehouse_alias,
            warehouse_alias.id == OrderWarehouseAddress.warehouse_address_id
        )

        .outerjoin(
            OrderFranchiseAddress,
            OrderFranchiseAddress.order_id == Order.id
        )

        .outerjoin(
            franchise_alias,
            franchise_alias.id == OrderFranchiseAddress.franchise_address_id
        )

        # =====================================================
        # STATUS TABLES
        # =====================================================

        .outerjoin(
            ConsigneeToDelivery,
            ConsigneeToDelivery.order_id == Order.id
        )

        .outerjoin(
            PickupToConsignees,
            PickupToConsignees.order_id == Order.id
        )

        .outerjoin(
            WarehouseToDelivery,
            WarehouseToDelivery.order_id == Order.id
        )

        .outerjoin(
            FranchiseToDelivery,
            FranchiseToDelivery.order_id == Order.id
        )
    )

    # =========================================================
    # FILTERS
    # =========================================================

    filters = []

    # =========================================================
    # DATE FILTER
    # =========================================================

    filters.append(
        func.date(Order.updated_at) == payload.date
    )

    # =========================================================
    # MAIN STATUS FILTER
    # =========================================================

    if status == "Dispatched":

        filters.append(
            or_(
                Order.status == "Dispatched",
                Order.status.ilike("Dispatched_%")
            )
        )

    elif status == "Warehouse":

        filters.append(
            or_(
                Order.status == "Warehouse",
                Order.status.ilike("Warehouse_%")
            )
        )

    else:

        filters.append(
            Order.status == status
        )

    # =========================================================
    # ROUTE STATUS FILTER
    # =========================================================
    #
    # ONLY CHECKS INSIDE THESE TABLES:
    #
    # WarehouseToDelivery
    # FranchiseToDelivery
    # PickupToConsignees
    # ConsigneeToDelivery
    #
    # =========================================================

    if route_status:

        filters.append(
            or_(

                WarehouseToDelivery.status == route_status,

                FranchiseToDelivery.status == route_status,

                PickupToConsignees.status == route_status,

                ConsigneeToDelivery.status == route_status,
            )
        )

    # =========================================================
    # SEARCH FILTER
    # =========================================================

    if search:

        filters.append(
            or_(

                # ORDER
                Order.order_number.ilike(f"%{search}%"),
                Order.status.ilike(f"%{search}%"),

                # CONSIGNEE
                Consignee.name.ilike(f"%{search}%"),
                Consignee.mobile.ilike(f"%{search}%"),
                Consignee.pincode.ilike(f"%{search}%"),

                # PICKUP
                PickupAddress.contact_name.ilike(f"%{search}%"),
                PickupAddress.nickname.ilike(f"%{search}%"),
                PickupAddress.phone.ilike(f"%{search}%"),
                PickupAddress.pincode.ilike(f"%{search}%"),

                # WAREHOUSE
                warehouse_alias.nickname.ilike(f"%{search}%"),
                warehouse_alias.contact_name.ilike(f"%{search}%"),
                warehouse_alias.phone.ilike(f"%{search}%"),
                warehouse_alias.pincode.ilike(f"%{search}%"),

                # FRANCHISE
                franchise_alias.name.ilike(f"%{search}%"),
                franchise_alias.phone.ilike(f"%{search}%"),
                franchise_alias.pincode.ilike(f"%{search}%"),
            )
        )

    # =========================================================
    # ROLE FILTER
    # =========================================================

    if role_name != "super_admin":

        filters.append(
            Order.created_by == current_user.id
        )

    # =========================================================
    # FINAL QUERY
    # =========================================================

    stmt = (
        stmt
        .where(and_(*filters))
        .order_by(Order.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)

    orders = result.scalars().unique().all()

    # =========================================================
    # COUNT QUERY
    # =========================================================

    count_stmt = (
        select(func.count(func.distinct(Order.id)))

        .select_from(Order)

        .join(
            Consignee,
            Order.consignee_id == Consignee.id
        )

        .join(
            PickupAddress,
            Order.pickup_address_id == PickupAddress.id
        )

        .outerjoin(
            OrderWarehouseAddress,
            OrderWarehouseAddress.order_id == Order.id
        )

        .outerjoin(
            warehouse_alias,
            warehouse_alias.id == OrderWarehouseAddress.warehouse_address_id
        )

        .outerjoin(
            OrderFranchiseAddress,
            OrderFranchiseAddress.order_id == Order.id
        )

        .outerjoin(
            franchise_alias,
            franchise_alias.id == OrderFranchiseAddress.franchise_address_id
        )

        .outerjoin(
            ConsigneeToDelivery,
            ConsigneeToDelivery.order_id == Order.id
        )

        .outerjoin(
            PickupToConsignees,
            PickupToConsignees.order_id == Order.id
        )

        .outerjoin(
            WarehouseToDelivery,
            WarehouseToDelivery.order_id == Order.id
        )

        .outerjoin(
            FranchiseToDelivery,
            FranchiseToDelivery.order_id == Order.id
        )

        .where(and_(*filters))
    )

    total_result = await db.execute(count_stmt)

    total = total_result.scalar() or 0

    # =========================================================
    # NO DATA
    # =========================================================

    if not orders:
        raise HTTPException(
            status_code=404,
            detail="No orders found"
        )

    total_pages = (total + limit - 1) // limit

    # =========================================================
    # RESPONSE
    # =========================================================

    return {
        "date": str(payload.date),

        "main_status": status,

        "route_status": route_status,

        "search": search,

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
                "id": order.id,

                "order_number": order.order_number,

                "status": order.status,

                "previous_status": order.previous_status,

                "order_type": order.order_type,

                "payment_method": order.payment_method,

                "order_value": float(order.order_value),

                "shipping_charge": float(order.shipping_charge),

                "total_weight_kg": float(order.total_weight_kg),

                "total_boxes": order.total_boxes,

                "created_at": order.created_at,

                "updated_at": order.updated_at,

                # =================================================
                # CONSIGNEE
                # =================================================

                "consignee": {
                    "name": order.consignee.name if order.consignee else None,
                    "mobile": order.consignee.mobile if order.consignee else None,
                    "pincode": order.consignee.pincode if order.consignee else None,
                    "city": order.consignee.city if order.consignee else None,
                    "state": order.consignee.state if order.consignee else None,
                },

                # =================================================
                # PICKUP
                # =================================================

                "pickup": {
                    "name": order.pickup_address.contact_name if order.pickup_address else None,
                    "nickname": order.pickup_address.nickname if order.pickup_address else None,
                    "phone": order.pickup_address.phone if order.pickup_address else None,
                    "pincode": order.pickup_address.pincode if order.pickup_address else None,
                    "city": order.pickup_address.city if order.pickup_address else None,
                    "state": order.pickup_address.state if order.pickup_address else None,
                },

                # =================================================
                # WAREHOUSES
                # =================================================

                "warehouses": [

                    {
                        "id": wh.warehouse_address.id,
                        "name": wh.warehouse_address.nickname,
                        "contact_name": wh.warehouse_address.contact_name,
                        "phone": wh.warehouse_address.phone,
                        "pincode": wh.warehouse_address.pincode,
                        "city": wh.warehouse_address.city,
                        "state": wh.warehouse_address.state,
                    }

                    for wh in order.warehouse_addresses
                    if wh.warehouse_address
                ],

                # =================================================
                # FRANCHISES
                # =================================================

                "franchises": [

                    {
                        "id": fr.franchise_address.id,
                        "name": fr.franchise_address.name,
                        "phone": fr.franchise_address.phone,
                        "pincode": fr.franchise_address.pincode,
                    }

                    for fr in order.franchise_addresses
                    if fr.franchise_address
                ],

                # =================================================
                # ITEMS
                # =================================================

                "items": [

                    {
                        "product_name": item.product_name,
                        "sku": item.sku,
                        "qty": item.qty,
                        "unit_price": float(item.unit_price),
                        "total": float(item.total),
                    }

                    for item in order.items
                ],
                "packages": [

                    {
                        "count": pkg.count,
                        "length_cm": float(pkg.length_cm),
                        "breadth_cm": float(pkg.breadth_cm),
                        "height_cm": float(pkg.height_cm),
                        "physical_weight_kg": float(pkg.physical_weight_kg),
                    }

                    for pkg in order.packages
                ],
            }

            for order in orders
        ]
    }
















@router.get("/counts")
async def get_all_order_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_order_counts(db, current_user)
    
    
   

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
    
    
    
    

    
from fastapi import status





@router.get("/track_orderwithbarcodeand_orderall_detailed/{barcode}")
async def track_order_by_barcode(
    barcode: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    decoded_barcode = barcode.strip()

    try:
        decoded_barcode = base64.b64decode(decoded_barcode).decode("utf-8")
    except Exception:
        pass
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.pickup_address),
            selectinload(Order.consignee),
            selectinload(Order.items),
            selectinload(Order.packages),
        )
        .where(Order.order_number == decoded_barcode)
    )

    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    warehouse_result = await db.execute(
        select(WarehouseToDelivery)
        .options(
            selectinload(WarehouseToDelivery.warehouse_address)
        )
        .where(WarehouseToDelivery.order_id == order.id)
    )
    warehouse_entries = warehouse_result.scalars().all()
    warehouse_data = []
    for warehouse in warehouse_entries:
        if warehouse.warehouse_address:
            warehouse_data.append({
                "id": warehouse.warehouse_address.id,
                "nickname": warehouse.warehouse_address.nickname,
                "contact_name": warehouse.warehouse_address.contact_name,
                "phone": warehouse.warehouse_address.phone,
                "email": warehouse.warehouse_address.email,
                "address_line_1": warehouse.warehouse_address.address_line_1,
                "address_line_2": warehouse.warehouse_address.address_line_2,
                "pincode": warehouse.warehouse_address.pincode,
                "city": warehouse.warehouse_address.city,
                "state": warehouse.warehouse_address.state,
                "country": warehouse.warehouse_address.country,
                "status": warehouse.status,
            })
    franchise_result = await db.execute(
        select(FranchiseToDelivery)
        .options(
            selectinload(FranchiseToDelivery.franchise_address)
        )
        .where(FranchiseToDelivery.order_id == order.id)
    )

    franchise_entries = franchise_result.scalars().all()
    franchise_data = []
    for franchise in franchise_entries:
        if franchise.franchise_address:
            franchise_data.append({
                "id": franchise.franchise_address.id,
                "franchise_code": franchise.franchise_address.franchise_code,
                "name": franchise.franchise_address.name,
                "email": franchise.franchise_address.email,
                "phone": franchise.franchise_address.phone,
                "address": franchise.franchise_address.address,
                "pincode": franchise.franchise_address.pincode,
                "preferred_service_area": franchise.franchise_address.preferred_service_area,
                "nearby_landmark": franchise.franchise_address.nearby_landmark,
                "status": franchise.status,
            })
    pickup_data = None
    if order.pickup_address:
        pickup_data = {
            "id": order.pickup_address.id,
            "nickname": order.pickup_address.nickname,
            "contact_name": order.pickup_address.contact_name,
            "phone": order.pickup_address.phone,
            "email": order.pickup_address.email,
            "address_line_1": order.pickup_address.address_line_1,
            "address_line_2": order.pickup_address.address_line_2,
            "pincode": order.pickup_address.pincode,
            "city": order.pickup_address.city,
            "state": order.pickup_address.state,
            "country": order.pickup_address.country,
        }
    consignee_data = None
    if order.consignee:
        consignee_data = {
            "id": order.consignee.id,
            "name": order.consignee.name,
            "mobile": order.consignee.mobile,
            "alternate_mobile": order.consignee.alternate_mobile,
            "email": order.consignee.email,
            "address_line_1": order.consignee.address_line_1,
            "address_line_2": order.consignee.address_line_2,
            "pincode": order.consignee.pincode,
            "city": order.consignee.city,
            "state": order.consignee.state,
        }
    items_data = []
    for item in order.items:
        items_data.append({
            "id": item.id,
            "product_name": item.product_name,
            "sku": item.sku,
            "unit_price": float(item.unit_price),
            "qty": item.qty,
            "total": float(item.total),
        })
    packages_data = []
    for package in order.packages:
        packages_data.append({
            "id": package.id,
            "count": package.count,
            "length_cm": float(package.length_cm),
            "breadth_cm": float(package.breadth_cm),
            "height_cm": float(package.height_cm),
            "vol_weight_kg": float(package.vol_weight_kg),
            "physical_weight_kg": float(package.physical_weight_kg),
        })
    return {
        "success": True,
        "order": {
            "order_id": order.id,
            "order_number": order.order_number,
            "barcode": order.barcode,
            "status": order.status,
            "payment_method": order.payment_method,
            "order_type": order.order_type,
            "order_value": float(order.order_value),
            "shipping_charge": float(order.shipping_charge),
            "total_weight_kg": float(order.total_weight_kg),
            "total_vol_weight_kg": float(order.total_vol_weight_kg),
            "applicable_weight_kg": float(order.applicable_weight_kg),
            "total_boxes": order.total_boxes,
            "created_at": order.created_at,
        },
        "pickup_address": pickup_data,
        "warehouse_addresses": warehouse_data,
        "franchise_addresses": franchise_data,
        "consignee": consignee_data,
        "items": items_data,
        "packages": packages_data,
    }




    









@router.delete("/delete-scanned-order_with_mistak/{id}/{orderid}")
async def delete_scanned_order(
    id: str,
    orderid:str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),):
    
    deleted_from = None
    order_id = None
    warehouse_result = await db.execute(select(WarehouseToDelivery).where(WarehouseToDelivery.warehouse_addresses_id == id,WarehouseToDelivery.order_id==orderid))
    warehouse_entry = warehouse_result.scalar_one_or_none()
    if warehouse_entry:
        order_result = await db.execute(select(Order).where(Order.id == warehouse_entry.order_id))
        order = order_result.scalar_one_or_none()
        if order:
           
            order.status = order.previous_status
            order.previous_status=OrderStatus.PROCESSING.value
            order.updated_at = datetime.now(IST)
        order_id = warehouse_entry.order_id
        await db.delete(warehouse_entry)
        deleted_from = "WarehouseToDelivery"
    if not deleted_from:
        franchise_result = await db.execute(select(FranchiseToDelivery).where(FranchiseToDelivery.franchise_addresses_id == id,FranchiseToDelivery.order_id==orderid))
        franchise_entry = franchise_result.scalar_one_or_none()
        if franchise_entry:
            order_result = await db.execute(select(Order).where(Order.id == franchise_entry.order_id))
            order = order_result.scalar_one_or_none()
            if order:
                order.status = order.previous_status
                order.previous_status=OrderStatus.DISPATCHED.value
                order.updated_at = datetime.now(IST)
            order_id = franchise_entry.order_id
            await db.delete(franchise_entry)
            deleted_from = "FranchiseToDelivery"
    if not deleted_from:
        pickup_result = await db.execute(select(PickupToConsignees).where(PickupToConsignees.pickup_addresses_id == id,ConsigneeToDelivery.order_id==orderid))
        pickup_entry = pickup_result.scalar_one_or_none()
        if pickup_entry:
            order_result = await db.execute(
                select(Order).where(Order.id == pickup_entry.order_id))
            order = order_result.scalar_one_or_none()
            if order:
                order.status = order.previous_status
                order.previous_status=OrderStatus.PICKED.value
                order.updated_at = datetime.now(IST)
            order_id = pickup_entry.order_id
            await db.delete(pickup_entry)
            deleted_from = "PickupToConsignees"
    if not deleted_from:
        consignee_result = await db.execute(select(ConsigneeToDelivery).where(ConsigneeToDelivery.consignee_id == id,ConsigneeToDelivery.order_id==orderid))
        consignee_entry = consignee_result.scalar_one_or_none()
        if consignee_entry:
            order_result = await db.execute(select(Order).where(Order.id == consignee_entry.order_id))
            order = order_result.scalar_one_or_none()
            if order:
                order.status = order.previous_status
                order.previous_status=OrderStatus.PROCESSING.value
                order.updated_at = datetime.now(IST)
            order_id = consignee_entry.order_id
            await db.delete(consignee_entry)
            deleted_from = "ConsigneeToDelivery"
    if not deleted_from:
        raise HTTPException(status_code=404,detail="No scanned data found with this ID")
    await db.commit()
    return {
        "success": True,
        "deleted_from": deleted_from,
        "deleted_id": id,
        "order_id": order_id,
    }    
    
    
    
    
    
    
    
    
@router.post("/orders/date-wise-all-status")
async def get_date_wise_all_status(
    payload: TodayStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    role_result = await db.execute(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == current_user.id))
    role_name = role_result.scalar_one_or_none()
    today = payload.date
    order_filters = [func.date(Order.updated_at) == today]
    if role_name != "super_admin":
        order_filters.append(Order.created_by == current_user.id)
    order_result = await db.execute(select(Order.status).where(*order_filters))
    order_statuses = [row[0] for row in order_result.all()]
    warehouse_filters = [func.date(WarehouseToDelivery.updated_at) == today]
    if role_name != "super_admin":
        warehouse_filters.append(WarehouseToDelivery.user_id == current_user.id)
    warehouse_result = await db.execute(select(WarehouseToDelivery.status).where(*warehouse_filters))
    warehouse_statuses = [row[0] for row in warehouse_result.all()]
    franchise_filters = [func.date(FranchiseToDelivery.updated_at) == today]
    if role_name != "super_admin":
        franchise_filters.append(FranchiseToDelivery.user_id == current_user.id)
    franchise_result = await db.execute(select(FranchiseToDelivery.status).where(*franchise_filters))
    franchise_statuses = [row[0] for row in franchise_result.all()]
    pickup_filters = [func.date(PickupToConsignees.updated_at) == today]
    if role_name != "super_admin":
        pickup_filters.append(PickupToConsignees.user_id == current_user.id)
    pickup_result = await db.execute(select(PickupToConsignees.status).where(*pickup_filters))
    pickup_statuses = [row[0] for row in pickup_result.all()]
    consignee_filters = [func.date(ConsigneeToDelivery.updated_at) == today]
    if role_name != "super_admin":
        consignee_filters.append(ConsigneeToDelivery.user_id == current_user.id)
    consignee_result = await db.execute(
        select(ConsigneeToDelivery.status)
        .where(*consignee_filters))
    consignee_statuses = [row[0] for row in consignee_result.all()]
    all_statuses = (order_statuses +warehouse_statuses +franchise_statuses +pickup_statuses +consignee_statuses)
    unique_statuses = list(set(all_statuses))
    return {
    "date": str(today),
    "statuses": unique_statuses
    }
    
   


class TodayStatusRequest(BaseModel):
    date: date
    status: str


@router.post("/orders/date-wise-status-address")
async def get_date_wise_status_address(
    payload: TodayStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):

    role_result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == current_user.id)
    )

    role_name = role_result.scalar_one_or_none()

    selected_date = payload.date
    selected_status = payload.status.strip()

    parts = selected_status.split("_")
    base_status = parts[0]
    has_suffix = len(parts) > 1

    addresses = []

    # =========================================================
    # PICKED STATUS
    # =========================================================

    if base_status == "Picked":

        filters = [
            func.date(PickupToConsignees.updated_at) == selected_date,
        ]

        if has_suffix:
            filters.append(
                PickupToConsignees.status == selected_status
            )
        else:
            filters.append(
                or_(
                    PickupToConsignees.status == "Picked",
                    PickupToConsignees.status.like("Picked\\_%")
                )
            )

        if role_name != "super_admin":
            filters.append(
                PickupToConsignees.user_id == current_user.id
            )

        result = await db.execute(
            select(
                PickupAddress.id,
                PickupAddress.nickname,
                PickupAddress.contact_name,
                PickupAddress.phone,
                PickupAddress.email,
                PickupAddress.address_line_1,
                PickupAddress.address_line_2,
                PickupAddress.city,
                PickupAddress.state,
                PickupAddress.country,
                PickupAddress.pincode,
                PickupToConsignees.status.label("status_found"),
            )
            .join(
                PickupAddress,
                PickupAddress.id == PickupToConsignees.pickup_addresses_id
            )
            .where(*filters)
            .distinct()
        )

        rows = result.all()

        for row in rows:
            addresses.append({
                "type": "pickup_address",
                "id": row.id,
                "nickname": row.nickname,
                "contact_name": row.contact_name,
                "phone": row.phone,
                "email": row.email,
                "address_line_1": row.address_line_1,
                "address_line_2": row.address_line_2,
                "city": row.city,
                "state": row.state,
                "country": row.country,
                "pincode": row.pincode,
                "status": row.status_found,
                "date": str(selected_date),
            })

    # =========================================================
    # WAREHOUSE STATUS
    # =========================================================

    elif base_status == "Warehouse":

        filters = [
            func.date(WarehouseToDelivery.updated_at) == selected_date,
        ]

        if has_suffix:
            filters.append(
                WarehouseToDelivery.status == selected_status
            )
        else:
            filters.append(
                or_(
                    WarehouseToDelivery.status == "Warehouse",
                    WarehouseToDelivery.status.like("Warehouse\\_%")
                )
            )

        if role_name != "super_admin":
            filters.append(
                WarehouseToDelivery.user_id == current_user.id
            )

        result = await db.execute(
            select(
                WareHouseAddress.id,
                WareHouseAddress.nickname,
                WareHouseAddress.contact_name,
                WareHouseAddress.phone,
                WareHouseAddress.email,
                WareHouseAddress.address_line_1,
                WareHouseAddress.address_line_2,
                WareHouseAddress.city,
                WareHouseAddress.state,
                WareHouseAddress.country,
                WareHouseAddress.pincode,
                WarehouseToDelivery.status.label("status_found"),
            )
            .join(
                WareHouseAddress,
                WareHouseAddress.id == WarehouseToDelivery.warehouse_addresses_id
            )
            .where(*filters)
            .distinct()
        )

        rows = result.all()

        for row in rows:
            addresses.append({
                "type": "warehouse_address",
                "id": row.id,
                "nickname": row.nickname,
                "contact_name": row.contact_name,
                "phone": row.phone,
                "email": row.email,
                "address_line_1": row.address_line_1,
                "address_line_2": row.address_line_2,
                "city": row.city,
                "state": row.state,
                "country": row.country,
                "pincode": row.pincode,
                "status": row.status_found,
                "date": str(selected_date),
            })

    # =========================================================
    # DISPATCHED STATUS
    # =========================================================

    elif base_status == "Dispatched":

        filters = [
            func.date(FranchiseToDelivery.updated_at) == selected_date,
        ]

        if has_suffix:
            filters.append(
                FranchiseToDelivery.status == selected_status
            )
        else:
            filters.append(
                or_(
                    FranchiseToDelivery.status == "Dispatched",
                    FranchiseToDelivery.status.like("Dispatched\\_%")
                )
            )

        if role_name != "super_admin":
            filters.append(
                FranchiseToDelivery.user_id == current_user.id
            )

        result = await db.execute(
            select(
                Franchise.id,
                Franchise.name,
                Franchise.phone,
                Franchise.email,
                Franchise.address,
                Franchise.pincode,
                Franchise.proposed_location,
                Franchise.detailed_business_address,
                Franchise.nearby_landmark,
                FranchiseToDelivery.status.label("status_found"),
            )
            .join(
                Franchise,
                Franchise.id == FranchiseToDelivery.franchise_addresses_id
            )
            .where(*filters)
            .distinct()
        )

        rows = result.all()

        for row in rows:
            addresses.append({
                "type": "franchise_address",
                "id": row.id,
                "name": row.name,
                "phone": row.phone,
                "email": row.email,
                "address": row.address,
                "pincode": row.pincode,
                "proposed_location": row.proposed_location,
                "detailed_business_address": row.detailed_business_address,
                "nearby_landmark": row.nearby_landmark,
                "status": row.status_found,
                "date": str(selected_date),
            })

    # =========================================================
    # INVALID STATUS
    # =========================================================

    else:
        return {
            "success": False,
            "message": "Invalid status",
            "supported_statuses": [
                "Picked",
                "Warehouse",
                "Dispatched"
            ]
        }

    # =========================================================
    # FINAL RESPONSE
    # =========================================================

    return {
        "success": True,
        "date": str(selected_date),
        "searched_status": selected_status,
        "total_unique_addresses": len(addresses),
        "addresses": addresses,
    }











from sqlalchemy import select, func, and_, desc
from app.models.order import BulkOrder
from app.schemas.bulkorders import BulkOrderDetailResponse,OrderPackageResponse,OrderItemResponse,OrderDetailResponse,DateRangeFilter

# ============= API 1: Get Bulk Order Details with All Orders =============

@router.get("/bulk-order/{bulk_order_id}", response_model=BulkOrderDetailResponse)
async def get_bulk_order_details(
    bulk_order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = (
        select(BulkOrder)
        .options(
            selectinload(BulkOrder.orders)
            .selectinload(Order.items),
            selectinload(BulkOrder.orders)
            .selectinload(Order.packages),
            selectinload(BulkOrder.orders)
            .selectinload(Order.pickup_address),
            selectinload(BulkOrder.orders)
            .selectinload(Order.consignee),
            selectinload(BulkOrder.orders)
            .selectinload(Order.warehouse_addresses)
            .selectinload(OrderWarehouseAddress.warehouse_address),
            selectinload(BulkOrder.orders)
            .selectinload(Order.franchise_addresses)
            .selectinload(OrderFranchiseAddress.franchise_address),
        )
        .where(BulkOrder.id == bulk_order_id)
    )
    
    result = await db.execute(stmt)
    bulk_order = result.scalar_one_or_none()
    
    if not bulk_order:
        raise HTTPException(status_code=404, detail="Bulk order not found")
    
    # Check authorization
    if bulk_order.created_by != current_user.id and current_user.role_name != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this bulk order")
    
    # Format orders with tracking history
    orders_data = []
    for order in bulk_order.orders:
        # Get tracking history for each order
        tracking_history = await get_order_tracking_history(db, order.id)
        
        orders_data.append({
            "id": order.id,
            "order_number": order.order_number,
            "order_type": order.order_type,
            "status": order.status,
            "previous_status": order.previous_status,
            "payment_method": order.payment_method,
            "cod_amount": float(order.cod_amount) if order.cod_amount else None,
            "to_pay_amount": float(order.to_pay_amount) if order.to_pay_amount else None,
            "order_value": float(order.order_value),
            "total_weight_kg": float(order.total_weight_kg),
            "total_vol_weight_kg": float(order.total_vol_weight_kg),
            "applicable_weight_kg": float(order.applicable_weight_kg),
            "total_boxes": order.total_boxes,
            "shipping_charge": float(order.shipping_charge),
            "gst_number": order.gst_number,
            "eway_bill_number": order.eway_bill_number,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "pickup_address": {
                "name": order.pickup_address.contact_name if order.pickup_address else None,
                "phone": order.pickup_address.phone if order.pickup_address else None,
                "address": order.pickup_address.address_line_1 if order.pickup_address else None,
                "pincode": order.pickup_address.pincode if order.pickup_address else None,
                "city": order.pickup_address.city if order.pickup_address else None,
                "state": order.pickup_address.state if order.pickup_address else None
            } if order.pickup_address else None,
            "delivery_address": {
                "name": order.consignee.name if order.consignee else None,
                "phone": order.consignee.mobile if order.consignee else None,
                "address": order.consignee.address_line_1 if order.consignee else None,
                "pincode": order.consignee.pincode if order.consignee else None,
                "city": order.consignee.city if order.consignee else None,
                "state": order.consignee.state if order.consignee else None
            } if order.consignee else None,
            "warehouse_addresses": [
                {
                    "name": wa.warehouse_address.nickname if wa.warehouse_address else None,
                    "pincode": wa.warehouse_address.pincode if wa.warehouse_address else None,
                    "city": wa.warehouse_address.city if wa.warehouse_address else None
                } for wa in order.warehouse_addresses if wa.warehouse_address
            ],
            "franchise_addresses": [
                {
                    "name": fa.franchise_address.name if fa.franchise_address else None,
                    "pincode": fa.franchise_address.pincode if fa.franchise_address else None
                } for fa in order.franchise_addresses if fa.franchise_address
            ],
            "items": [
                {
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "unit_price": float(item.unit_price),
                    "qty": item.qty,
                    "total": float(item.total)
                } for item in order.items
            ],
            "packages": [
                {
                    "count": pkg.count,
                    "length_cm": float(pkg.length_cm),
                    "breadth_cm": float(pkg.breadth_cm),
                    "height_cm": float(pkg.height_cm),
                    "vol_weight_kg": float(pkg.vol_weight_kg),
                    "physical_weight_kg": float(pkg.physical_weight_kg)
                } for pkg in order.packages
            ],
            "tracking_history": tracking_history
        })
    
    return {
        "id": bulk_order.id,
        "file_name": bulk_order.file_name,
        "order_type": bulk_order.order_type,
        "status": bulk_order.status,
        "total_orders": bulk_order.total_orders,
        "successful_orders": bulk_order.successful_orders,
        "failed_orders": bulk_order.failed_orders,
        "created_by": bulk_order.created_by,
        "franchise_id": bulk_order.franchise_id,
        "created_at": bulk_order.created_at.isoformat(),
        "updated_at": bulk_order.updated_at.isoformat(),
        "orders": orders_data
    }


# ============= Helper Function for Tracking History =============




async def get_order_tracking_history(db: AsyncSession, order_id: str) -> List[Dict]:
    # Get all tracking events
    pickup_events = await db.execute(
        select(PickupToConsignees).where(PickupToConsignees.order_id == order_id))
    warehouse_events = await db.execute(
        select(WarehouseToDelivery).where(WarehouseToDelivery.order_id == order_id))
    franchise_events = await db.execute(
        select(FranchiseToDelivery).where(FranchiseToDelivery.order_id == order_id))
    delivery_events = await db.execute(
        select(ConsigneeToDelivery).where(ConsigneeToDelivery.order_id == order_id))
    tracking_history = []
    for event in pickup_events.scalars().all():
        tracking_history.append({
            "stage": "Pickup",
            "status": event.status,
            "pincode": event.pincode,
            "timestamp": event.created_at.isoformat() if event.created_at else None
        })
    for event in warehouse_events.scalars().all():
        tracking_history.append({
            "stage": "Warehouse",
            "status": event.status,
            "pincode": event.pincode,
            "timestamp": event.created_at.isoformat() if event.created_at else None
        })
    for event in franchise_events.scalars().all():
        tracking_history.append({
            "stage": "Franchise",
            "status": event.status,
            "pincode": event.pincode,
            "timestamp": event.created_at.isoformat() if event.created_at else None
        })
    for event in delivery_events.scalars().all():
        tracking_history.append({
            "stage": "Delivery",
            "status": event.status,
            "pincode": event.pincode,
            "timestamp": event.created_at.isoformat() if event.created_at else None
        })
    tracking_history.sort(key=lambda x: x.get("timestamp", ""))
    return tracking_history


# ============= API 2: Get Single Bag Details with All Orders =============

@router.get("/bag/{bag_id_or_barcode}")
async def get_bag_details(
    bag_id_or_barcode: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = (
        select(Bag)
        .options(
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.items),
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.packages),
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.pickup_address),
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.consignee),
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.warehouse_addresses)
            .selectinload(OrderWarehouseAddress.warehouse_address),
            selectinload(Bag.bag_orders)
            .selectinload(BagOrder.order)
            .selectinload(Order.franchise_addresses)
            .selectinload(OrderFranchiseAddress.franchise_address),
        )
        .where((Bag.id == bag_id_or_barcode) | (Bag.bag_number == bag_id_or_barcode)))
    result = await db.execute(stmt)
    bag = result.scalar_one_or_none()
    if not bag:
        raise HTTPException(status_code=404, detail="Bag not found")
    if bag.created_by != current_user.id and current_user.role_name != "super_admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this bag")
    orders_data = []
    for bag_order in bag.bag_orders:
        order = bag_order.order
        if not order:
            continue
        tracking_history = await get_order_tracking_history(db, order.id)
        orders_data.append({
            "order_id": order.id,
            "order_number": order.order_number,
            "scanned_at": bag_order.scanned_at.isoformat() if bag_order.scanned_at else None,
            "order_details": {
                "order_type": order.order_type,
                "status": order.status,
                "previous_status": order.previous_status,
                "payment_method": order.payment_method,
                "cod_amount": float(order.cod_amount) if order.cod_amount else None,
                "to_pay_amount": float(order.to_pay_amount) if order.to_pay_amount else None,
                "order_value": float(order.order_value),
                "total_weight_kg": float(order.total_weight_kg),
                "total_vol_weight_kg": float(order.total_vol_weight_kg),
                "applicable_weight_kg": float(order.applicable_weight_kg),
                "total_boxes": order.total_boxes,
                "shipping_charge": float(order.shipping_charge),
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat()
            },
            "pickup_address": {
                "name": order.pickup_address.contact_name if order.pickup_address else None,
                "phone": order.pickup_address.phone if order.pickup_address else None,
                "address": order.pickup_address.address_line_1 if order.pickup_address else None,
                "pincode": order.pickup_address.pincode if order.pickup_address else None,
                "city": order.pickup_address.city if order.pickup_address else None,
                "state": order.pickup_address.state if order.pickup_address else None
            } if order.pickup_address else None,
            "delivery_address": {
                "name": order.consignee.name if order.consignee else None,
                "phone": order.consignee.mobile if order.consignee else None,
                "address": order.consignee.address_line_1 if order.consignee else None,
                "pincode": order.consignee.pincode if order.consignee else None,
                "city": order.consignee.city if order.consignee else None,
                "state": order.consignee.state if order.consignee else None
            } if order.consignee else None,
            "items": [
                {
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "unit_price": float(item.unit_price),
                    "qty": item.qty,
                    "total": float(item.total)
                } for item in order.items
            ],
            "packages": [
                {
                    "count": pkg.count,
                    "length_cm": float(pkg.length_cm),
                    "breadth_cm": float(pkg.breadth_cm),
                    "height_cm": float(pkg.height_cm),
                    "vol_weight_kg": float(pkg.vol_weight_kg),
                    "physical_weight_kg": float(pkg.physical_weight_kg)
                } for pkg in order.packages
            ],
            "tracking_history": tracking_history
        })
    bag_scan_history = []
    for bag_order in bag.bag_orders:
        if bag_order.scanned_at:
            bag_scan_history.append({
                "order_id": bag_order.order_id,
                "scanned_at": bag_order.scanned_at.isoformat()})
    return {
        "bag_id": bag.id,
        "bag_number": bag.bag_number,
        "bag_status": bag.status,
        "bag_pincode": bag.pincode,
        "total_orders": bag.total_orders,
        "created_by": bag.created_by,
        "created_at": bag.created_at.isoformat(),
        "updated_at": bag.updated_at.isoformat(),
        "bag_scan_history": bag_scan_history,
        "orders": orders_data,
        "summary": {
            "total_orders_in_bag": len(orders_data),
            "orders_by_status": {
                "picked": sum(1 for o in orders_data if o["order_details"]["status"] == "Picked"),
                "warehouse": sum(1 for o in orders_data if "Warehouse" in o["order_details"]["status"]),
                "dispatched": sum(1 for o in orders_data if "Dispatched" in o["order_details"]["status"]),
                "delivered": sum(1 for o in orders_data if o["order_details"]["status"] == "Delivered")
            },
            "total_order_value": sum(o["order_details"]["order_value"] for o in orders_data),
            "total_shipping_charge": sum(o["order_details"]["shipping_charge"] for o in orders_data)
        }
    }


# ============= API 3: Get All Bags with Date Filter =============

@router.post("/bags/filter")
async def get_bags_with_date_filter(
    filter_data: DateRangeFilter,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Bag).options(selectinload(Bag.bag_orders).selectinload(BagOrder.order))
    conditions = []
    if filter_data.start_date:
        start_datetime = datetime.combine(filter_data.start_date, datetime.min.time())
        conditions.append(Bag.created_at >= start_datetime)
    if filter_data.end_date:
        end_datetime = datetime.combine(filter_data.end_date, datetime.max.time())
        conditions.append(Bag.created_at <= end_datetime)
    if filter_data.status:
        conditions.append(Bag.status == filter_data.status)
    if filter_data.pincode:
        conditions.append(Bag.pincode == filter_data.pincode)
    if current_user.role_name != "super_admin":
        conditions.append(Bag.created_by == current_user.id)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    count_stmt = select(func.count()).select_from(Bag)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total_count = await db.execute(count_stmt)
    total = total_count.scalar()
    stmt = stmt.order_by(desc(Bag.created_at))
    stmt = stmt.offset((filter_data.page - 1) * filter_data.limit)
    stmt = stmt.limit(filter_data.limit)
    result = await db.execute(stmt)
    bags = result.scalars().all()
    bags_data = []
    for bag in bags:
        orders_in_bag = [bo.order for bo in bag.bag_orders if bo.order]
        picked_count = 0
        warehouse_count = 0
        dispatched_count = 0
        delivered_count = 0
        for o in orders_in_bag:
            if o:
                if o.status == "Picked":
                    picked_count += 1
                elif "Warehouse" in o.status:
                    warehouse_count += 1
                elif "Dispatched" in o.status:
                    dispatched_count += 1
                elif o.status == "Delivered":
                    delivered_count += 1
        bags_data.append({
            "bag_id": bag.id,
            "bag_number": bag.bag_number,
            "bag_status": bag.status,
            "bag_pincode": bag.pincode,
            "total_orders": bag.total_orders,
            "created_by": bag.created_by,
            "created_at": bag.created_at.isoformat(),
            "updated_at": bag.updated_at.isoformat(),
            "order_summary": {
                "total_orders_in_bag": len(orders_in_bag),
                "orders_by_status": {
                    "picked": picked_count,
                    "warehouse": warehouse_count,
                    "dispatched": dispatched_count,
                    "delivered": delivered_count
                },
                "total_order_value": sum(float(o.order_value) for o in orders_in_bag if o),
                "recent_orders": [
                    {
                        "order_number": o.order_number,
                        "status": o.status,
                        "order_value": float(o.order_value),
                        "created_at": o.created_at.isoformat() if o.created_at else None
                    } for o in orders_in_bag[:5] if o
                ]
            }
        })
    user_info = {
        "user_id": current_user.id,
        "user_role": current_user.role_name,
        "view_scope": "all_bags" if current_user.role_name == "admin" else "my_bags_only"
    }
    return {
        "user_info": user_info,
        "total": total,
        "page": filter_data.page,
        "limit": filter_data.limit,
        "total_pages": (total + filter_data.limit - 1) // filter_data.limit if total > 0 else 0,
        "bags": bags_data,
        "filter_applied": {
            "start_date": filter_data.start_date.isoformat() if filter_data.start_date else None,
            "end_date": filter_data.end_date.isoformat() if filter_data.end_date else None,
            "status": filter_data.status,
            "pincode": filter_data.pincode
        }
    }
    
    
    
    
    
    
    
    
    


@router.get("/bag/{bag_id}/barcode-image")
async def get_bag_barcode_image(
    bag_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Bag).where(Bag.id == bag_id)
    result = await db.execute(stmt)
    bag = result.scalar_one_or_none()
    
    if not bag:
        raise HTTPException(status_code=404, detail=f"Bag with ID {bag_id} not found")
    barcode_class = barcode.get_barcode_class('code128')
    buffer = BytesIO()
    barcode_obj = barcode_class(bag.bag_number, writer=ImageWriter())
    barcode_obj.write(buffer, options={"write_text": True, "font_size": 10})
    media_type = "image/png"
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="barcode_{bag.bag_number}.{format}"',"Cache-Control": "no-cache"})    