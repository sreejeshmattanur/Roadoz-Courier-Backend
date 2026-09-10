from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class ParcelPaymentMethod(str, Enum):
    PREPAID = "Prepaid"
    COD = "COD"
    TO_PAY = "To Pay"
    CREDIT = "Credit"


class ParcelROV(str, Enum):
    OWNER_RISK = "owner_risk"
    CARRIER_RISK = "carrier_risk"


class ParcelServiceType(str, Enum):
    SURFACE = "Surface"
    AIR = "Air"
    EXPRESS = "Express"


# ── Senders ──────────────────────────────────────────────────────────────────

class ParcelSenderCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    mobile: Optional[str] = Field(None, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class ParcelSenderUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    mobile: Optional[str] = Field(None, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class ParcelSenderOut(BaseModel):
    id: str
    name: Optional[str] = None
    mobile: Optional[str] = None
    alternate_mobile: Optional[str] = None
    email: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    franchise_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ParcelSenderListResponse(BaseModel):
    items: List[ParcelSenderOut]
    total: int
    page: int
    limit: int
    pages: int


# ── Receivers ────────────────────────────────────────────────────────────────

class ParcelReceiverCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    mobile: Optional[str] = Field(None, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class ParcelReceiverUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    mobile: Optional[str] = Field(None, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class ParcelReceiverOut(BaseModel):
    id: str
    name: Optional[str] = None
    mobile: Optional[str] = None
    alternate_mobile: Optional[str] = None
    email: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    franchise_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ParcelReceiverListResponse(BaseModel):
    items: List[ParcelReceiverOut]
    total: int
    page: int
    limit: int
    pages: int


# ── Create ────────────────────────────────────────────────────────────────────

class ParcelOrderCreate(BaseModel):
    sender_id: Optional[str] = None
    receiver_id: Optional[str] = None

    payment_method: Optional[ParcelPaymentMethod] = None
    cod_amount: Optional[float] = Field(None, ge=0)
    prepaid_amount: Optional[float] = Field(None, ge=0)
    to_pay_amount: Optional[float] = Field(None, ge=0)
    credit_amount: Optional[float] = Field(None, ge=0)

    rov: Optional[ParcelROV] = None
    order_value: Optional[float] = Field(0, ge=0)

    service_type: Optional[ParcelServiceType] = ParcelServiceType.SURFACE
    freight_charge: Optional[float] = Field(0, ge=0)
    freight_gst: Optional[float] = Field(0, ge=0)
    total_freight: Optional[float] = Field(0, ge=0)
    extra_charge: Optional[float] = Field(0, ge=0)

    # Package info
    weight_kg: Optional[float] = Field(None, ge=0)
    length_cm: Optional[float] = Field(None, ge=0)
    breadth_cm: Optional[float] = Field(None, ge=0)
    height_cm: Optional[float] = Field(None, ge=0)
    total_boxes: Optional[int] = Field(1, ge=1)

    # Product
    product_name: Optional[str] = Field(None, max_length=255)
    qty: Optional[int] = Field(1, ge=1)

    # Misc
    gst_number: Optional[str] = Field(None, max_length=20)
    eway_bill_number: Optional[str] = Field(None, max_length=30)
    invoicenumber: Optional[int] = None
    insurance: Optional[float] = Field(None, ge=0)
    regional_area: Optional[float] = Field(0, ge=0)
    remarks: Optional[str] = Field(None, max_length=500)


# ── Update (all optional) ─────────────────────────────────────────────────────

class ParcelOrderUpdate(BaseModel):
    sender_id: Optional[str] = None
    receiver_id: Optional[str] = None

    payment_method: Optional[ParcelPaymentMethod] = None
    cod_amount: Optional[float] = Field(None, ge=0)
    prepaid_amount: Optional[float] = Field(None, ge=0)
    to_pay_amount: Optional[float] = Field(None, ge=0)
    credit_amount: Optional[float] = Field(None, ge=0)

    rov: Optional[ParcelROV] = None
    order_value: Optional[float] = Field(None, ge=0)

    service_type: Optional[ParcelServiceType] = None
    freight_charge: Optional[float] = Field(None, ge=0)
    freight_gst: Optional[float] = Field(None, ge=0)
    total_freight: Optional[float] = Field(None, ge=0)
    extra_charge: Optional[float] = Field(None, ge=0)

    weight_kg: Optional[float] = Field(None, ge=0)
    length_cm: Optional[float] = Field(None, ge=0)
    breadth_cm: Optional[float] = Field(None, ge=0)
    height_cm: Optional[float] = Field(None, ge=0)
    total_boxes: Optional[int] = Field(None, ge=1)

    product_name: Optional[str] = Field(None, max_length=255)
    qty: Optional[int] = Field(None, ge=1)

    gst_number: Optional[str] = Field(None, max_length=20)
    eway_bill_number: Optional[str] = Field(None, max_length=30)
    invoicenumber: Optional[int] = None
    insurance: Optional[float] = Field(None, ge=0)
    regional_area: Optional[float] = Field(None, ge=0)
    remarks: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=50)


# ── Out (response) ────────────────────────────────────────────────────────────

class ParcelOrderOut(BaseModel):
    id: str
    order_number: str
    barcode: Optional[str] = None
    status: str

    sender_id: Optional[str] = None
    receiver_id: Optional[str] = None
    
    sender: Optional[ParcelSenderOut] = None
    receiver: Optional[ParcelReceiverOut] = None

    # Payment
    payment_method: Optional[str] = None
    cod_amount: Optional[float] = None
    prepaid_amount: Optional[float] = None
    to_pay_amount: Optional[float] = None
    credit_amount: Optional[float] = None
    rov: Optional[str] = None
    order_value: Optional[float] = None

    # Freight
    service_type: Optional[str] = None
    freight_charge: Optional[float] = None
    freight_gst: Optional[float] = None
    total_freight: Optional[float] = None
    extra_charge: Optional[float] = None

    # Package
    weight_kg: Optional[float] = None
    length_cm: Optional[float] = None
    breadth_cm: Optional[float] = None
    height_cm: Optional[float] = None
    total_boxes: Optional[int] = None

    # Product
    product_name: Optional[str] = None
    sku: Optional[str] = None
    qty: Optional[int] = None

    # Misc
    gst_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    invoicenumber: Optional[int] = None
    insurance: Optional[float] = None
    regional_area: Optional[float] = None
    remarks: Optional[str] = None

    # Meta
    franchise_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ParcelOrderListResponse(BaseModel):
    items: List[ParcelOrderOut]
    total: int
    page: int
    limit: int
    pages: int

class ParcelOrderBarcodeListRequest(BaseModel):
    barcodes: List[str] = Field(..., description="List of parcel order barcodes")

