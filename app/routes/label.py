from fastapi import APIRouter, Depends, status,Body
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.models.order import Order
from app.services.order_service import _resolve_franchise_id
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel,Field
from sqlalchemy.orm import selectinload





router = APIRouter(prefix="/label", tags=["Label"])

# =========================================================
# Request/Response Models
# =========================================================

class OrderItemDetails(BaseModel):
    product_name: str
    sku: Optional[str] = None
    unit_price: float
    qty: int
    total: float

class OrderPackageDetails(BaseModel):
    count: int
    length_cm: float
    breadth_cm: float
    height_cm: float
    vol_weight_kg: float
    physical_weight_kg: float

class AddressDetails(BaseModel):
    name: str
    contact_name: str
    phone: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    country: str
    pincode: str

class OrderLabelResponse(BaseModel):
    success: bool
    order_id: str
    order_number: str
    awb_number: str
    ref_no: str
    pcs: int
    order_type: str
    payment_method: str
    cod_amount: Optional[float] = None
    to_pay_amount: Optional[float] = None
    order_value: float
    shipping_charge: float
    status: str
    from_address: AddressDetails
    to_address: AddressDetails
    return_address: AddressDetails
    items: List[OrderItemDetails]
    packages: List[OrderPackageDetails]
    subtotal: float
    total_weight_kg: float
    total_vol_weight_kg: float
    applicable_weight_kg: float
    order_date: datetime
    invoice_date: str
    notes: Optional[str] = None
    return_instruction: Optional[str] = None


class BulkOrderError(BaseModel):
    order_id: str
    error: str
    status_code: int


class BulkOrderLabelResponse(BaseModel):
    success: bool
    total_orders: int
    successful_orders: int
    failed_orders: int
    orders: List[OrderLabelResponse]
    errors: List[BulkOrderError]
    generated_at: datetime


# =========================================================
# Helper Function
# =========================================================

async def get_single_order_label_data(
    db: AsyncSession, 
    order_id: str, 
    current_user: User
) -> dict:
    """Get complete order data for label generation for a single order"""
    
    # Get order with all relationships
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.packages),
            selectinload(Order.pickup_address),
            selectinload(Order.consignee)
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    
    # Check permissions
    franchise_id = await _resolve_franchise_id(db, current_user)
    is_global = not franchise_id
    
    if not is_global and order.franchise_id != franchise_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for order {order_id}"
        )
    
    # Calculate subtotal from items
    subtotal = sum(item.total for item in order.items) if order.items else float(order.order_value)
    
    # Get return address (same as pickup address)
    return_address = order.pickup_address
    
    # Prepare response
    return {
        "success": True,
        "order_id": order.id,
        "order_number": order.order_number,
        "awb_number": order.order_number,
        "ref_no": order.order_number,
        "pcs": order.total_boxes,
        "order_type": order.order_type,
        "payment_method": order.payment_method,
        "cod_amount": float(order.cod_amount) if order.cod_amount else None,
        "to_pay_amount": float(order.to_pay_amount) if order.to_pay_amount else None,
        "order_value": float(order.order_value),
        "shipping_charge": float(order.shipping_charge),
        "status": order.status,
        "from_address": {
            "name": order.pickup_address.nickname,
            "contact_name": order.pickup_address.contact_name,
            "phone": order.pickup_address.phone,
            "email": order.pickup_address.email,
            "address_line_1": order.pickup_address.address_line_1,
            "address_line_2": order.pickup_address.address_line_2 or "",
            "city": order.pickup_address.city,
            "state": order.pickup_address.state,
            "country": order.pickup_address.country,
            "pincode": order.pickup_address.pincode,
        },
        "to_address": {
            "name": order.consignee.name,
            "contact_name": order.consignee.name,
            "phone": order.consignee.mobile,
            "email": order.consignee.email,
            "address_line_1": order.consignee.address_line_1,
            "address_line_2": order.consignee.address_line_2 or "",
            "city": order.consignee.city,
            "state": order.consignee.state,
            "country": "India",
            "pincode": order.consignee.pincode,
        },
        "return_address": {
            "name": return_address.nickname,
            "contact_name": return_address.contact_name,
            "phone": return_address.phone,
            "email": return_address.email,
            "address_line_1": return_address.address_line_1,
            "address_line_2": return_address.address_line_2 or "",
            "city": return_address.city,
            "state": return_address.state,
            "country": return_address.country,
            "pincode": return_address.pincode,
        },
        "items": [
            {
                "product_name": item.product_name,
                "sku": item.sku,
                "unit_price": float(item.unit_price),
                "qty": item.qty,
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
                "vol_weight_kg": float(pkg.vol_weight_kg),
                "physical_weight_kg": float(pkg.physical_weight_kg),
            }
            for pkg in order.packages
        ],
        "subtotal": float(subtotal),
        "total_weight_kg": float(order.total_weight_kg),
        "total_vol_weight_kg": float(order.total_vol_weight_kg),
        "applicable_weight_kg": float(order.applicable_weight_kg),
        "order_date": order.created_at,
        "invoice_date": order.created_at.strftime("%d/%m/%Y"),
        "notes": f"If undelivered return to: {order.pickup_address.nickname}, {order.pickup_address.address_line_1}, {order.pickup_address.city}, {order.pickup_address.state}, {order.pickup_address.pincode}, India Mobile: {order.pickup_address.phone}",
        "return_instruction": f"For complaints & queries please contact {order.pickup_address.phone}",
    }


# =========================================================
# API 1: Single Order Label
# =========================================================

@router.get("/{order_id}/label", response_model=OrderLabelResponse)
async def get_order_label(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    """Generate shipping label/invoice for a single order"""
    return await get_single_order_label_data(db, order_id, current_user)


# =========================================================
# API 2: Bulk Orders Label - Using List in Body
# =========================================================

@router.post("/bulk/labels", response_model=BulkOrderLabelResponse)
async def get_bulk_order_labels(
    order_ids: List[str] = Body(..., description="List of order IDs", example=["order-id-1", "order-id-2", "order-id-3"]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    if len(order_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 order IDs allowed per request"
        )
    successful_orders = []
    errors = []
    for order_id in order_ids:
        try:
            order_data = await get_single_order_label_data(db, order_id, current_user)
            successful_orders.append(OrderLabelResponse(**order_data))
        except HTTPException as e:
            errors.append(BulkOrderError(
                order_id=order_id,
                error=e.detail,
                status_code=e.status_code
            ))
        except Exception as e:
            errors.append(BulkOrderError(
                order_id=order_id,
                error=str(e),
                status_code=500
            ))
    
    return BulkOrderLabelResponse(
        success=len(errors) == 0,
        total_orders=len(order_ids),
        successful_orders=len(successful_orders),
        failed_orders=len(errors),
        orders=successful_orders,
        errors=errors,
        generated_at=datetime.now()
    )