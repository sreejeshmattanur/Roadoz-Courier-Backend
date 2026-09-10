"""
Parcel Order routes - POST /parcel-orders, GET, PUT, DELETE.
No auto calculations. Everything is manually entered by the user.
Role-scoped: Admin sees all, Franchise scoped to their franchise,
Warehouse scoped to their warehouse.
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.models.parcel_order import ParcelOrder, ParcelSender, ParcelReceiver
from app.schemas.parcel_order import (
    ParcelOrderCreate,
    ParcelOrderUpdate,
    ParcelOrderOut,
    ParcelOrderListResponse,
    ParcelOrderBarcodeListRequest,
    ParcelSenderCreate,
    ParcelSenderUpdate,
    ParcelSenderOut,
    ParcelSenderListResponse,
    ParcelReceiverCreate,
    ParcelReceiverUpdate,
    ParcelReceiverOut,
    ParcelReceiverListResponse,
)

router = APIRouter(prefix="/parcel-orders", tags=["Parcel Orders"])


# ── helpers ──────────────────────────────────────────────────────────────────

async def _resolve_franchise_id(db: AsyncSession, user: User) -> Optional[str]:
    from app.services.order_service import _resolve_franchise_id as _rfi
    return await _rfi(db, user)


async def _resolve_warehouse_id(db: AsyncSession, user: User) -> Optional[str]:
    from app.services.order_service import _resolve_warehouse_id as _rwi
    return await _rwi(db, user)


def _scope_filters(model, franchise_id, warehouse_id) -> list:
    """Build ownership filters based on caller scope."""
    if franchise_id:
        return [model.franchise_id == franchise_id]
    if warehouse_id:
        return [model.warehouse_id == warehouse_id]
    return []  # admin – no filter, see all


async def _generate_parcel_number(db: AsyncSession) -> str:
    """
    Continue from the shared ORD-XXXXX sequence so barcodes are unique across
    both regular orders and parcel orders.
    """
    from app.services.order_service import _generate_order_number
    return await _generate_order_number(db)


def _to_parcel_out(parcel: ParcelOrder) -> ParcelOrderOut:
    return ParcelOrderOut.model_validate(parcel)


@router.post("/by-barcodes", response_model=list[ParcelOrderOut])
async def list_parcel_orders_by_barcodes(
    request: ParcelOrderBarcodeListRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:view")),
):
    """
    Fetch a list of ParcelOrders given their barcodes.
    Applies RBAC filtering based on franchise/warehouse.
    """
    if not request.barcodes:
        return []

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    filters = _scope_filters(ParcelOrder, franchise_id, warehouse_id)

    query = select(ParcelOrder).where(
        or_(
            ParcelOrder.barcode.in_(request.barcodes),
            ParcelOrder.order_number.in_(request.barcodes)
        )
    ).options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query)
    orders = result.scalars().all()
    return [_to_parcel_out(o) for o in orders]


# ── SENDERS ──────────────────────────────────────────────────────────────────

@router.post("/senders/create", response_model=ParcelSenderOut, status_code=201)
async def create_parcel_sender(
    data: ParcelSenderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcelsenders:create")),
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    sender = ParcelSender(
        **data.model_dump(exclude_unset=True),
        created_by=current_user.id,
        franchise_id=franchise_id,
        warehouse_id=warehouse_id,
    )
    db.add(sender)
    await db.commit()
    await db.refresh(sender)
    return sender


@router.get("/senders/list", response_model=ParcelSenderListResponse)
async def list_parcel_senders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcelsenders:view")),
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    filters = _scope_filters(ParcelSender, franchise_id, warehouse_id)

    if search:
        like = f"%{search}%"
        filters.append(
            or_(
                ParcelSender.name.ilike(like),
                ParcelSender.mobile.ilike(like),
            )
        )

    where = and_(*filters) if filters else True

    total = (await db.execute(select(func.count()).select_from(ParcelSender).where(where))).scalar_one()

    offset = (page - 1) * limit
    rows = (
        await db.execute(
            select(ParcelSender)
            .where(where)
            .order_by(ParcelSender.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return ParcelSenderListResponse(
        items=rows,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/senders/getonebyone/{sender_id}", response_model=ParcelSenderOut)
async def get_parcel_sender(
    sender_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcelsenders:view")),
):
    sender = (await db.execute(select(ParcelSender).where(ParcelSender.id == sender_id))).scalar_one_or_none()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and sender.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and sender.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return sender


@router.put("/senders/update/{sender_id}", response_model=ParcelSenderOut)
async def update_parcel_sender(
    sender_id: str,
    data: ParcelSenderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcelsenders:edit")),
):
    sender = (await db.execute(select(ParcelSender).where(ParcelSender.id == sender_id))).scalar_one_or_none()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and sender.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and sender.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sender, field, value)

    await db.commit()
    await db.refresh(sender)
    return sender


@router.delete("/senders/delete/{sender_id}")
async def delete_parcel_sender(
    sender_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcelsenders:delete")),
):
    sender = (await db.execute(select(ParcelSender).where(ParcelSender.id == sender_id))).scalar_one_or_none()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and sender.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and sender.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(sender)
    await db.commit()
    return {"success": True, "message": "Sender deleted"}


# ── RECEIVERS ────────────────────────────────────────────────────────────────

@router.post("/receivers/create", response_model=ParcelReceiverOut, status_code=201)
async def create_parcel_receiver(
    data: ParcelReceiverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("receiverparcel:create")),
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    receiver = ParcelReceiver(
        **data.model_dump(exclude_unset=True),
        created_by=current_user.id,
        franchise_id=franchise_id,
        warehouse_id=warehouse_id,
    )
    db.add(receiver)
    await db.commit()
    await db.refresh(receiver)
    return receiver


@router.get("/receivers/list", response_model=ParcelReceiverListResponse)
async def list_parcel_receivers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("receiverparcel:view")),
):
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    filters = _scope_filters(ParcelReceiver, franchise_id, warehouse_id)

    if search:
        like = f"%{search}%"
        filters.append(
            or_(
                ParcelReceiver.name.ilike(like),
                ParcelReceiver.mobile.ilike(like),
            )
        )

    where = and_(*filters) if filters else True

    total = (await db.execute(select(func.count()).select_from(ParcelReceiver).where(where))).scalar_one()

    offset = (page - 1) * limit
    rows = (
        await db.execute(
            select(ParcelReceiver)
            .where(where)
            .order_by(ParcelReceiver.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return ParcelReceiverListResponse(
        items=rows,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/receivers/getonebyone/{receiver_id}", response_model=ParcelReceiverOut)
async def get_parcel_receiver(
    receiver_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("receiverparcel:view")),
):
    receiver = (await db.execute(select(ParcelReceiver).where(ParcelReceiver.id == receiver_id))).scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and receiver.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and receiver.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return receiver


@router.put("/receivers/update/{receiver_id}", response_model=ParcelReceiverOut)
async def update_parcel_receiver(
    receiver_id: str,
    data: ParcelReceiverUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("receiverparcel:edit")),
):
    receiver = (await db.execute(select(ParcelReceiver).where(ParcelReceiver.id == receiver_id))).scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and receiver.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and receiver.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(receiver, field, value)

    await db.commit()
    await db.refresh(receiver)
    return receiver


@router.delete("/receivers/delete/{receiver_id}")
async def delete_parcel_receiver(
    receiver_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("receiverparcel:delete")),
):
    receiver = (await db.execute(select(ParcelReceiver).where(ParcelReceiver.id == receiver_id))).scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id
    if not is_global:
        if franchise_id and receiver.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and receiver.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(receiver)
    await db.commit()
    return {"success": True, "message": "Receiver deleted"}


# ── ORDER CREATE ─────────────────────────────────────────────────────────────

@router.post("/create", response_model=ParcelOrderOut, status_code=201)
async def create_parcel_order(
    data: ParcelOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:create")),
):
    """
    Create a new parcel order.
    - NO backend calculations – freight, weights etc. are whatever the user provides.
    - Sender and receiver IDs are passed, linking to existing Sender/Receiver records.
    - Order number / barcode continue from the shared ORD- sequence.
    """
    from app.utils.barcode import generate_barcode_base64
    from app.services.order_service import generate_sku

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    # Validate sender/receiver exist
    if data.sender_id:
        sender = (await db.execute(select(ParcelSender).where(ParcelSender.id == data.sender_id))).scalar_one_or_none()
        if not sender:
            raise HTTPException(status_code=404, detail=f"Sender {data.sender_id} not found")
    if data.receiver_id:
        receiver = (await db.execute(select(ParcelReceiver).where(ParcelReceiver.id == data.receiver_id))).scalar_one_or_none()
        if not receiver:
            raise HTTPException(status_code=404, detail=f"Receiver {data.receiver_id} not found")

    order_number = await _generate_parcel_number(db)
    barcode_b64 = generate_barcode_base64(order_number)
    
    sku = await generate_sku(db)

    # Flatten payment amounts based on method
    cod_amount = prepaid_amount = to_pay_amount = credit_amount = None
    pm = data.payment_method
    if pm:
        if pm.value == "COD":
            cod_amount = data.cod_amount
        elif pm.value == "Prepaid":
            prepaid_amount = data.prepaid_amount
        elif pm.value == "To Pay":
            to_pay_amount = data.to_pay_amount
        elif pm.value == "Credit":
            credit_amount = data.credit_amount

    parcel = ParcelOrder(
        order_number=order_number,
        barcode=barcode_b64,
        franchise_id=franchise_id,
        warehouse_id=warehouse_id,
        created_by=current_user.id,

        sender_id=data.sender_id,
        receiver_id=data.receiver_id,

        # Payment
        payment_method=pm.value if pm else None,
        cod_amount=cod_amount,
        prepaid_amount=prepaid_amount,
        to_pay_amount=to_pay_amount,
        credit_amount=credit_amount,
        rov=data.rov.value if data.rov else None,
        order_value=data.order_value,

        # Freight (manual)
        service_type=data.service_type.value if data.service_type else None,
        freight_charge=data.freight_charge,
        freight_gst=data.freight_gst,
        total_freight=data.total_freight,
        extra_charge=data.extra_charge,

        # Package
        weight_kg=data.weight_kg,
        length_cm=data.length_cm,
        breadth_cm=data.breadth_cm,
        height_cm=data.height_cm,
        total_boxes=data.total_boxes,

        # Product
        product_name=data.product_name,
        sku=sku,
        qty=data.qty,

        # Misc
        gst_number=data.gst_number,
        eway_bill_number=data.eway_bill_number,
        invoicenumber=data.invoicenumber,
        insurance=data.insurance,
        regional_area=data.regional_area,
        remarks=data.remarks,
    )

    db.add(parcel)
    await db.commit()
    # refresh and load relationships
    await db.refresh(parcel)
    parcel = (
        await db.execute(
            select(ParcelOrder)
            .where(ParcelOrder.id == parcel.id)
            .options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
        )
    ).scalar_one()

    return _to_parcel_out(parcel)


# ── ORDER LIST ───────────────────────────────────────────────────────────────

@router.get("/list", response_model=ParcelOrderListResponse)
async def list_parcel_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by order_number, sender/receiver name, mobile or pincode"),
    status: Optional[str] = Query(None),
    payment_method: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:view")),
):
    """List parcel orders, scoped by role (Admin / Franchise / Warehouse)."""
    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)

    filters = _scope_filters(ParcelOrder, franchise_id, warehouse_id)

    if status:
        filters.append(ParcelOrder.status == status)
    if payment_method:
        filters.append(ParcelOrder.payment_method == payment_method)
        
    query = select(ParcelOrder).outerjoin(ParcelOrder.sender).outerjoin(ParcelOrder.receiver)

    if search:
        like = f"%{search}%"
        filters.append(
            or_(
                ParcelOrder.order_number.ilike(like),
                ParcelSender.name.ilike(like),
                ParcelSender.mobile.ilike(like),
                ParcelReceiver.name.ilike(like),
                ParcelReceiver.mobile.ilike(like),
                ParcelReceiver.pincode.ilike(like),
                ParcelSender.pincode.ilike(like),
            )
        )

    where = and_(*filters) if filters else True

    # Count using the joins
    total = (await db.execute(
        select(func.count(ParcelOrder.id))
        .select_from(ParcelOrder)
        .outerjoin(ParcelOrder.sender)
        .outerjoin(ParcelOrder.receiver)
        .where(where)
    )).scalar_one()

    offset = (page - 1) * limit
    rows = (
        await db.execute(
            query
            .where(where)
            .options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
            .order_by(ParcelOrder.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return ParcelOrderListResponse(
        items=[_to_parcel_out(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


# ── ORDER GET SINGLE ──────────────────────────────────────────────────────────

@router.get("/getonebyone/{parcel_id}", response_model=ParcelOrderOut)
async def get_parcel_order(
    parcel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:view")),
):
    """Retrieve a single parcel order by ID."""
    parcel = (
        await db.execute(
            select(ParcelOrder)
            .where(ParcelOrder.id == parcel_id)
            .options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
        )
    ).scalar_one_or_none()

    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel order not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id

    if not is_global:
        if franchise_id and parcel.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and parcel.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return _to_parcel_out(parcel)


# ── ORDER UPDATE ──────────────────────────────────────────────────────────────

@router.put("/update/{parcel_id}", response_model=ParcelOrderOut)
async def update_parcel_order(
    parcel_id: str,
    data: ParcelOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:edit")),
):
    """
    Update a parcel order.
    Only fields provided in the request body are changed (PATCH semantics
    applied via model_dump(exclude_unset=True)).
    """
    parcel = (
        await db.execute(
            select(ParcelOrder)
            .where(ParcelOrder.id == parcel_id)
            .options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
        )
    ).scalar_one_or_none()

    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel order not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id

    if not is_global:
        if franchise_id and parcel.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and parcel.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Validate sender/receiver if updating
    if data.sender_id is not None:
        sender = (await db.execute(select(ParcelSender).where(ParcelSender.id == data.sender_id))).scalar_one_or_none()
        if not sender:
            raise HTTPException(status_code=404, detail=f"Sender {data.sender_id} not found")
    if data.receiver_id is not None:
        receiver = (await db.execute(select(ParcelReceiver).where(ParcelReceiver.id == data.receiver_id))).scalar_one_or_none()
        if not receiver:
            raise HTTPException(status_code=404, detail=f"Receiver {data.receiver_id} not found")

    update_data = data.model_dump(exclude_unset=True)

    # Flatten payment method enum
    if "payment_method" in update_data and update_data["payment_method"] is not None:
        pm = update_data["payment_method"]
        update_data["payment_method"] = pm.value if hasattr(pm, "value") else pm

    for field, value in update_data.items():
        if hasattr(parcel, field):
            val = value.value if hasattr(value, "value") else value
            setattr(parcel, field, val)

    await db.commit()
    await db.refresh(parcel)
    
    # Reload with new relationships
    parcel = (
        await db.execute(
            select(ParcelOrder)
            .where(ParcelOrder.id == parcel.id)
            .options(selectinload(ParcelOrder.sender), selectinload(ParcelOrder.receiver))
        )
    ).scalar_one()
    return _to_parcel_out(parcel)


# ── ORDER DELETE ──────────────────────────────────────────────────────────────

@router.delete("/delete/{parcel_id}", status_code=http_status.HTTP_200_OK)
async def delete_parcel_order(
    parcel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("parcel:delete")),
):
    """Delete a parcel order."""
    parcel = (
        await db.execute(select(ParcelOrder).where(ParcelOrder.id == parcel_id))
    ).scalar_one_or_none()

    if not parcel:
        raise HTTPException(status_code=404, detail="Parcel order not found")

    franchise_id = await _resolve_franchise_id(db, current_user)
    warehouse_id = await _resolve_warehouse_id(db, current_user)
    is_global = not franchise_id and not warehouse_id

    if not is_global:
        if franchise_id and parcel.franchise_id != franchise_id:
            raise HTTPException(status_code=403, detail="Access denied")
        elif warehouse_id and parcel.warehouse_id != warehouse_id:
            raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(parcel)
    await db.commit()
    return {"success": True, "message": f"Parcel order {parcel_id} deleted successfully"}
