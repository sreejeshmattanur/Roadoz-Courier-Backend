from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.dependencies.consigeeuser import get_current_user
from app.models.consigeeauth import AuthUser
from app.models.order import Order, OrderItem, OrderPackage, BagOrder, Bag
from app.models.pickup_address import PickupAddress
from app.models.consignee import Consignee
from app.models.warehouse import WareHouseAddress, OrderWarehouseAddress
from app.models.franchise import Franchise, OrderFranchiseAddress
from app.schemas.consigeeuserorder import PickupAddressResponse,ConsigneeResponse,WarehouseAddressResponse,FranchiseAddressResponse,ItemResponse,PackageResponse,WeightSummaryResponse,OrderListResponse,PaginatedOrdersResponse
from app.routes.order import PickupToConsignees,WarehouseToDelivery,FranchiseToDelivery,ConsigneeToDelivery





router = APIRouter(prefix="/consignee/orders", tags=["Consignee Orders"])



def build_tracking_history(order) -> List[dict]:
    """Build tracking history from order data"""
    tracking_history = []
    
    # 1. Pickup stage - Order Created / Picked
    tracking_history.append({
        "stage": "Pickup",
        "status": "Picked",
        "pincode": order.pickup_address.pincode if order.pickup_address else None,
        "timestamp": order.created_at
    })
    
    # 2. Warehouse stages (if warehouse addresses exist)
    if order.warehouse_addresses:
        for idx, warehouse_rel in enumerate(order.warehouse_addresses):
            if warehouse_rel.warehouse_address:
                warehouse = warehouse_rel.warehouse_address
                status = "Warehouse" if idx == 0 else f"Warehouse_{idx + 1}"
                tracking_history.append({
                    "stage": "Warehouse",
                    "status": status,
                    "pincode": warehouse.pincode,
                    "timestamp": order.created_at  # Use actual timestamps if available
                })
    
    # 3. Delivery stage - Current status
    if order.status == "Delivered":
        tracking_history.append({
            "stage": "Delivery",
            "status": "Delivered",
            "pincode": order.consignee.pincode if order.consignee else None,
            "timestamp": order.updated_at
        })
    else:
        # Add current status as delivery stage
        tracking_history.append({
            "stage": "Delivery",
            "status": order.status,
            "pincode": order.consignee.pincode if order.consignee else None,
            "timestamp": order.updated_at
        })
    
    return tracking_history


# ============== API Endpoints ==============

@router.get("/my-orders", response_model=PaginatedOrdersResponse)
async def get_my_orders(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=50, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by order number"),
):
    """
    Get all orders for the authenticated consignee user.
    Requires valid JWT token in Authorization header.
    """
    
    # Find consignee by user_id
    consignee_result = await db.execute(
        select(Consignee).where(Consignee.email == current_user.email)
    )
    consignee = consignee_result.scalar_one_or_none()
    
    if not consignee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consignee profile not found"
        )
    
    # Build base query
    query = select(Order).where(Order.consignee_id == consignee.id)
    
    if status_filter:
        query = query.where(Order.status == status_filter)
    
    if search:
        query = query.where(Order.order_number.ilike(f"%{search}%"))
    
    # Get total count
    count_query = select(Order).where(Order.consignee_id == consignee.id)
    if status_filter:
        count_query = count_query.where(Order.status == status_filter)
    if search:
        count_query = count_query.where(Order.order_number.ilike(f"%{search}%"))
    
    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())
    
    # Apply pagination
    query = query.order_by(desc(Order.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    
    # Load relationships
    query = query.options(
        selectinload(Order.pickup_address),
        selectinload(Order.consignee),
        selectinload(Order.items),
        selectinload(Order.packages),
        selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
        selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
        selectinload(Order.bag_orders).selectinload(BagOrder.bag),
    )
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # Build response
    order_responses = []
    for order in orders:
        # Pickup address
        pickup_data = None
        if order.pickup_address:
            pickup_data = PickupAddressResponse(
                id=order.pickup_address.id,
                nickname=order.pickup_address.nickname,
                contact_name=order.pickup_address.contact_name,
                phone=order.pickup_address.phone,
                email=order.pickup_address.email,
                address_line_1=order.pickup_address.address_line_1,
                address_line_2=order.pickup_address.address_line_2,
                pincode=order.pickup_address.pincode,
                city=order.pickup_address.city,
                state=order.pickup_address.state,
                country=order.pickup_address.country,
                active=order.pickup_address.active,
                is_primary=order.pickup_address.is_primary,
                created_at=order.pickup_address.created_at,
                updated_at=order.pickup_address.updated_at
            )
        
        # Consignee
        consignee_data = None
        if order.consignee:
            consignee_data = ConsigneeResponse(
                id=order.consignee.id,
                name=order.consignee.name,
                mobile=order.consignee.mobile,
                alternate_mobile=order.consignee.alternate_mobile,
                email=order.consignee.email,
                address_line_1=order.consignee.address_line_1,
                address_line_2=order.consignee.address_line_2,
                pincode=order.consignee.pincode,
                city=order.consignee.city,
                state=order.consignee.state,
                status=order.consignee.status,
                created_at=order.consignee.created_at,
                updated_at=order.consignee.updated_at
            )
        
        # Warehouse addresses
        warehouse_addresses = []
        for warehouse_rel in order.warehouse_addresses:
            if warehouse_rel.warehouse_address:
                warehouse = warehouse_rel.warehouse_address
                warehouse_addresses.append(WarehouseAddressResponse(
                    name=warehouse.nickname,
                    pincode=warehouse.pincode,
                    city=warehouse.city
                ))
        
        # Franchise addresses
        franchise_addresses = []
        for franchise_rel in order.franchise_addresses:
            if franchise_rel.franchise_address:
                franchise = franchise_rel.franchise_address
                franchise_addresses.append(FranchiseAddressResponse(
                    name=franchise.name,
                    pincode=franchise.pincode,
                    city=franchise.city if hasattr(franchise, 'city') else ""
                ))
        
        # Items
        items_data = []
        for item in order.items:
            items_data.append(ItemResponse(
                id=item.id,
                product_name=item.product_name,
                sku=item.sku,
                unit_price=float(item.unit_price),
                qty=item.qty,
                total=float(item.total)
            ))
        
        # Packages
        packages_data = []
        for package in order.packages:
            packages_data.append(PackageResponse(
                id=package.id,
                count=package.count,
                length_cm=float(package.length_cm),
                breadth_cm=float(package.breadth_cm),
                height_cm=float(package.height_cm),
                vol_weight_kg=float(package.vol_weight_kg),
                physical_weight_kg=float(package.physical_weight_kg)
            ))
        
        # Weight summary
        weight_summary = WeightSummaryResponse(
            applicable_weight_kg=float(order.applicable_weight_kg),
            total_boxes=order.total_boxes,
            total_weight_kg=float(order.total_weight_kg),
            total_vol_weight_kg=float(order.total_vol_weight_kg)
        )
        
        # Tracking history
        tracking_history = build_tracking_history(order)
        
        order_responses.append(OrderListResponse(
            id=order.id,
            order_number=order.order_number,
            order_type=order.order_type,
            status=order.status,
            previous_status=order.previous_status,
            payment_method=order.payment_method,
            cod_amount=float(order.cod_amount) if order.cod_amount else None,
            to_pay_amount=float(order.to_pay_amount) if order.to_pay_amount else None,
            order_value=float(order.order_value),
            total_weight_kg=float(order.total_weight_kg),
            total_vol_weight_kg=float(order.total_vol_weight_kg),
            applicable_weight_kg=float(order.applicable_weight_kg),
            total_boxes=order.total_boxes,
            shipping_charge=float(order.shipping_charge),
            gst_number=order.gst_number,
            eway_bill_number=order.eway_bill_number,
            barcode=order.barcode,
            created_at=order.created_at,
            updated_at=order.updated_at,
            pickup_address=pickup_data,
            consignee=consignee_data,
            warehouse_addresses=warehouse_addresses,
            franchise_addresses=franchise_addresses,
            items=items_data,
            packages=packages_data,
            weight_summary=weight_summary,
            tracking_history=tracking_history
        ))
    
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    
    return PaginatedOrdersResponse(
        items=order_responses,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )




@router.get("/{order_id}")
async def get_order_detail(
    order_id: str,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information of a specific order with complete tracking history.
    Shows where the order was scanned and reached at each stage based on actual scan records.
    """
    
    consignee_result = await db.execute(
        select(Consignee).where(Consignee.email == current_user.email)
    )
    consignee = consignee_result.scalar_one_or_none()
    
    if not consignee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consignee profile not found"
        )
    
    query = select(Order).where(
        Order.id == order_id,
        Order.consignee_id == consignee.id
    ).options(
        selectinload(Order.pickup_address),
        selectinload(Order.consignee),
        selectinload(Order.items),
        selectinload(Order.packages),
        selectinload(Order.warehouse_addresses).selectinload(OrderWarehouseAddress.warehouse_address),
        selectinload(Order.franchise_addresses).selectinload(OrderFranchiseAddress.franchise_address),
        selectinload(Order.bag_orders).selectinload(BagOrder.bag),
    )
    
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # ========== GET ACTUAL SCAN RECORDS ==========
    
    # Get Pickup scans
    pickup_scans = await db.execute(
        select(PickupToConsignees)
        .where(PickupToConsignees.order_id == order.id)
        .order_by(PickupToConsignees.created_at)
    )
    pickup_scans = pickup_scans.scalars().all()
    
    # Get Warehouse scans
    warehouse_scans = await db.execute(
        select(WarehouseToDelivery)
        .where(WarehouseToDelivery.order_id == order.id)
        .order_by(WarehouseToDelivery.created_at)
    )
    warehouse_scans = warehouse_scans.scalars().all()
    
    # Get Franchise scans
    franchise_scans = await db.execute(
        select(FranchiseToDelivery)
        .where(FranchiseToDelivery.order_id == order.id)
        .order_by(FranchiseToDelivery.created_at)
    )
    franchise_scans = franchise_scans.scalars().all()
    
    # Get Delivery scans
    delivery_scans = await db.execute(
        select(ConsigneeToDelivery)
        .where(ConsigneeToDelivery.order_id == order.id)
        .order_by(ConsigneeToDelivery.created_at)
    )
    delivery_scans = delivery_scans.scalars().all()
    
    # ========== BUILD TRACKING HISTORY FROM ACTUAL SCANS ==========
    
    tracking_history = []
    
    # 1. ORDER CREATED (always first)
    tracking_history.append({
        "stage": "Order Created",
        "status": "Processing",
        "status_display": "Order Created",
        "description": f"Order {order.order_number} has been created",
        "location": order.pickup_address.city if order.pickup_address else "System",
        "address": order.pickup_address.address_line_1 if order.pickup_address else None,
        "city": order.pickup_address.city if order.pickup_address else None,
        "state": order.pickup_address.state if order.pickup_address else None,
        "pincode": order.pickup_address.pincode if order.pickup_address else None,
        "contact_name": order.pickup_address.contact_name if order.pickup_address else None,
        "contact_phone": order.pickup_address.phone if order.pickup_address else None,
        "timestamp": order.created_at,
        "formatted_date": order.created_at.strftime("%d %b %Y, %I:%M %p") if order.created_at else None,
        "is_current": False,
        "icon": "📦",
        "scan_id": None
    })
    
    # 2. PICKUP SCANS
    for scan in pickup_scans:
        tracking_history.append({
            "stage": "Pickup",
            "status": "Picked Up",
            "status_display": "Picked Up",
            "description": f"Order picked up from {order.pickup_address.nickname if order.pickup_address else 'pickup location'}",
            "location": order.pickup_address.city if order.pickup_address else None,
            "address": order.pickup_address.address_line_1 if order.pickup_address else None,
            "city": order.pickup_address.city if order.pickup_address else None,
            "state": order.pickup_address.state if order.pickup_address else None,
            "pincode": scan.pincode,
            "contact_name": order.pickup_address.contact_name if order.pickup_address else None,
            "contact_phone": order.pickup_address.phone if order.pickup_address else None,
            "timestamp": scan.created_at,
            "formatted_date": scan.created_at.strftime("%d %b %Y, %I:%M %p") if scan.created_at else None,
            "is_current": False,
            "icon": "📤",
            "scan_id": scan.id,
            "scan_type": "pickup"
        })
    
    # 3. WAREHOUSE SCANS
    for idx, scan in enumerate(warehouse_scans):
        # Get warehouse details
        warehouse = None
        if scan.warehouse_address:
            warehouse = scan.warehouse_address
        
        status_name = "Warehouse" if idx == 0 else f"Warehouse {idx + 1}"
        is_current = (idx == len(warehouse_scans) - 1 and 
                     order.status in ["Warehouse", "In_transit", "Ofd", "Delivered"])
        
        tracking_history.append({
            "stage": "Warehouse",
            "status": scan.status,
            "status_display": f"Reached {warehouse.nickname if warehouse else 'Warehouse'}",
            "description": f"Order arrived at {warehouse.nickname if warehouse else 'warehouse'}",
            "location": warehouse.city if warehouse else scan.pincode,
            "address": warehouse.address_line_1 if warehouse else None,
            "city": warehouse.city if warehouse else None,
            "state": warehouse.state if warehouse else None,
            "pincode": scan.pincode,
            "contact_name": warehouse.contact_name if warehouse else None,
            "contact_phone": warehouse.phone if warehouse else None,
            "timestamp": scan.created_at,
            "formatted_date": scan.created_at.strftime("%d %b %Y, %I:%M %p") if scan.created_at else None,
            "is_current": is_current,
            "icon": "🏪",
            "scan_id": scan.id,
            "scan_type": "warehouse"
        })
    
    # 4. FRANCHISE SCANS
    for idx, scan in enumerate(franchise_scans):
        franchise = None
        if scan.franchise_address:
            franchise = scan.franchise_address
        
        is_current = (idx == len(franchise_scans) - 1 and 
                     order.status in ["Manifested", "In_transit", "Ofd", "Delivered"])
        
        tracking_history.append({
            "stage": "Franchise",
            "status": scan.status,
            "status_display": f"Reached {franchise.name if franchise else 'Franchise'}",
            "description": f"Order arrived at {franchise.name if franchise else 'franchise'}",
            "location": franchise.city if franchise and hasattr(franchise, 'city') else franchise.preferred_service_area if franchise else scan.pincode,
            "address": franchise.address if franchise and hasattr(franchise, 'address') else None,
            "city": franchise.city if franchise and hasattr(franchise, 'city') else None,
            "state": franchise.state if franchise and hasattr(franchise, 'state') else None,
            "pincode": scan.pincode,
            "contact_name": franchise.name if franchise else None,
            "contact_phone": franchise.phone if franchise else None,
            "timestamp": scan.created_at,
            "formatted_date": scan.created_at.strftime("%d %b %Y, %I:%M %p") if scan.created_at else None,
            "is_current": is_current,
            "icon": "🏢",
            "scan_id": scan.id,
            "scan_type": "franchise"
        })
    
    # 5. DELIVERY SCANS
    for idx, scan in enumerate(delivery_scans):
        consignee = order.consignee
        
        tracking_history.append({
            "stage": "Delivery",
            "status": "Delivered",
            "status_display": "Delivered Successfully",
            "description": f"Order delivered to {consignee.name if consignee else 'customer'}",
            "location": consignee.city if consignee else scan.pincode,
            "address": f"{consignee.address_line_1} {consignee.address_line_2 or ''}" if consignee else None,
            "city": consignee.city if consignee else None,
            "state": consignee.state if consignee else None,
            "pincode": scan.pincode,
            "contact_name": consignee.name if consignee else None,
            "contact_phone": consignee.mobile if consignee else None,
            "timestamp": scan.created_at,
            "formatted_date": scan.created_at.strftime("%d %b %Y, %I:%M %p") if scan.created_at else None,
            "is_current": True,
            "icon": "✅",
            "scan_id": scan.id,
            "scan_type": "delivery"
        })
    
    # If no scan records found, use order status to determine current location
    if not tracking_history:
        tracking_history.append({
            "stage": "Order Created",
            "status": order.status,
            "status_display": order.status,
            "description": f"Order status: {order.status}",
            "location": order.pickup_address.city if order.pickup_address else "System",
            "address": None,
            "city": order.pickup_address.city if order.pickup_address else None,
            "state": order.pickup_address.state if order.pickup_address else None,
            "pincode": order.pickup_address.pincode if order.pickup_address else None,
            "contact_name": None,
            "contact_phone": None,
            "timestamp": order.created_at,
            "formatted_date": order.created_at.strftime("%d %b %Y, %I:%M %p") if order.created_at else None,
            "is_current": True,
            "icon": "📦",
            "scan_id": None,
            "scan_type": None
        })
    
    # ========== IDENTIFY CURRENT LOCATION ==========
    
    # Find the latest scan (current location)
    current_scan = None
    for track in reversed(tracking_history):
        if track.get("scan_id"):
            current_scan = track
            break
    
    # If no scan found, use order status
    if not current_scan:
        current_scan = tracking_history[-1] if tracking_history else None
    
    # ========== BUILD RESPONSE ==========
    
    response = {
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
        "barcode": order.barcode,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }
    
    # Pickup address
    if order.pickup_address:
        response["pickup_address"] = {
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
            "active": order.pickup_address.active,
            "is_primary": order.pickup_address.is_primary,
            "created_at": order.pickup_address.created_at,
            "updated_at": order.pickup_address.updated_at
        }
    
    # Consignee
    if order.consignee:
        response["consignee"] = {
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
            "status": order.consignee.status,
            "created_at": order.consignee.created_at,
            "updated_at": order.consignee.updated_at
        }
    
    # Warehouse addresses
    response["warehouse_addresses"] = []
    for warehouse_rel in order.warehouse_addresses:
        if warehouse_rel.warehouse_address:
            warehouse = warehouse_rel.warehouse_address
            response["warehouse_addresses"].append({
                "name": warehouse.nickname,
                "pincode": warehouse.pincode,
                "city": warehouse.city,
                "address": warehouse.address_line_1
            })
    
    # Franchise addresses
    response["franchise_addresses"] = []
    for franchise_rel in order.franchise_addresses:
        if franchise_rel.franchise_address:
            franchise = franchise_rel.franchise_address
            response["franchise_addresses"].append({
                "name": franchise.name,
                "pincode": franchise.pincode,
                "city": franchise.city if hasattr(franchise, 'city') else "",
                "address": franchise.address if hasattr(franchise, 'address') else None
            })
    
    # Items
    response["items"] = []
    for item in order.items:
        response["items"].append({
            "id": item.id,
            "product_name": item.product_name,
            "sku": item.sku,
            "unit_price": float(item.unit_price),
            "qty": item.qty,
            "total": float(item.total)
        })
    
    # Packages
    response["packages"] = []
    for package in order.packages:
        response["packages"].append({
            "id": package.id,
            "count": package.count,
            "length_cm": float(package.length_cm),
            "breadth_cm": float(package.breadth_cm),
            "height_cm": float(package.height_cm),
            "vol_weight_kg": float(package.vol_weight_kg),
            "physical_weight_kg": float(package.physical_weight_kg)
        })
    
    # Weight summary
    response["weight_summary"] = {
        "applicable_weight_kg": float(order.applicable_weight_kg),
        "total_boxes": order.total_boxes,
        "total_weight_kg": float(order.total_weight_kg),
        "total_vol_weight_kg": float(order.total_vol_weight_kg)
    }
    
    # ========== TRACKING HISTORY ==========
    response["tracking_history"] = tracking_history
    
    # ========== CURRENT LOCATION ==========
    if current_scan:
        response["current_location"] = {
            "status": order.status,
            "status_display": current_scan.get("status_display", order.status),
            "stage": current_scan.get("stage"),
            "location": current_scan.get("location"),
            "address": current_scan.get("address"),
            "city": current_scan.get("city"),
            "pincode": current_scan.get("pincode"),
            "contact_name": current_scan.get("contact_name"),
            "contact_phone": current_scan.get("contact_phone"),
            "timestamp": current_scan.get("formatted_date"),
            "icon": current_scan.get("icon", "📦"),
            "scan_type": current_scan.get("scan_type")
        }
    else:
        response["current_location"] = {
            "status": order.status,
            "status_display": order.status,
            "stage": "Unknown",
            "location": None,
            "address": None,
            "city": None,
            "pincode": None,
            "contact_name": None,
            "contact_phone": None,
            "timestamp": None,
            "icon": "📦",
            "scan_type": None
        }
    
    # ========== TRACKING SUMMARY ==========
    response["tracking_summary"] = {
        "total_scans": len([t for t in tracking_history if t.get("scan_id")]),
        "pickup_scans": len(pickup_scans),
        "warehouse_scans": len(warehouse_scans),
        "franchise_scans": len(franchise_scans),
        "delivery_scans": len(delivery_scans),
        "order_status": order.status,
        "last_updated": order.updated_at.strftime("%d %b %Y, %I:%M %p") if order.updated_at else None
    }
    
    return response