from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.models.order import OrderStatus
from datetime import date
# ── Enums ──────────────────────────────────────────────────────────────────


class OrderType(str, Enum):
    B2C = "B2C"
    B2B = "B2B"
    INTERNATIONAL = "International"


class PaymentMethod(str, Enum):
    COD = "COD"
    PREPAID = "Prepaid"
    TO_PAY = "To Pay"


class ROV(str, Enum):
    OWNER_RISK = "owner_risk"
    CARRIER_RISK = "carrier_risk"


# ── Pickup Address ─────────────────────────────────────────────────────────


class PickupAddressCreate(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100)
    contact_name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=1, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: str = Field(..., min_length=1, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: str = Field(..., min_length=1, max_length=10)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    country: str = Field("India", max_length=100)


class PickupAddressOut(BaseModel):
    id: str
    nickname: str
    contact_name: str
    phone: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    pincode: str
    city: str
    state: str
    country: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PickupAddressListResponse(BaseModel):
    items: List[PickupAddressOut]
    total: int


# ── Consignee ──────────────────────────────────────────────────────────────


class ConsigneeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    mobile: str = Field(..., min_length=1, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: str = Field(..., min_length=1, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: str = Field(..., min_length=1, max_length=10)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)


class ConsigneeOut(BaseModel):
    id: str
    name: str
    mobile: str
    alternate_mobile: Optional[str] = None
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    pincode: str
    city: str
    state: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConsigneeListResponse(BaseModel):
    items: List[ConsigneeOut]
    total: int


# ── Order Items (Product Details) ──────────────────────────────────────────


class OrderItemCreate(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=255)
    sku: Optional[str] = Field(None, max_length=100)
    unit_price: float = Field(..., gt=0)
    qty: int = Field(..., ge=1)
    total: float = Field(..., gt=0)


class OrderItemOut(BaseModel):
    id: str
    product_name: str
    sku: Optional[str] = None
    unit_price: float
    qty: int
    total: float

    model_config = {"from_attributes": True}


# ── Order Packages (Package Details) ───────────────────────────────────────


class OrderPackageCreate(BaseModel):
    count: int = Field(1, ge=1, description="Number of boxes")
    length_cm: float = Field(..., gt=0)
    breadth_cm: float = Field(..., gt=0)
    height_cm: float = Field(..., gt=0)
    vol_weight_kg: float = Field(..., ge=0, description="Volumetric weight (B2C dividend 5000)")
    physical_weight_kg: float = Field(..., gt=0)


class OrderPackageOut(BaseModel):
    id: str
    count: int
    length_cm: float
    breadth_cm: float
    height_cm: float
    vol_weight_kg: float
    physical_weight_kg: float

    model_config = {"from_attributes": True}


# ── Weight Summary (read-only, computed) ───────────────────────────────────


class WeightSummary(BaseModel):
    applicable_weight_kg: float
    total_boxes: int
    total_weight_kg: float
    total_vol_weight_kg: float


# ── Order Create ───────────────────────────────────────────────────────────


class OrderCreate(BaseModel):
    order_type: OrderType
    pickup_address_id: str
    consignee_id: str
    warehouse_addresses_id:Optional[str] = None
    payment_method: PaymentMethod
    cod_amount: Optional[float] = Field(None, ge=0, description="Required when payment_method is COD")
    to_pay_amount: Optional[float] = Field(None, ge=0, description="Required when payment_method is To Pay")
    rov: ROV

    order_value: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _validate_payment_amounts(self):
        if self.payment_method == PaymentMethod.COD and self.cod_amount is None:
            raise ValueError("cod_amount is required when payment_method is COD")
        if self.payment_method == PaymentMethod.TO_PAY and self.to_pay_amount is None:
            raise ValueError("to_pay_amount is required when payment_method is To Pay")
        if self.payment_method == PaymentMethod.COD:
            self.to_pay_amount = None
        elif self.payment_method == PaymentMethod.TO_PAY:
            self.cod_amount = None
        elif self.payment_method == PaymentMethod.PREPAID:
            self.cod_amount = None
            self.to_pay_amount = None
        return self

    items: List[OrderItemCreate] = Field(..., min_length=1)
    packages: List[OrderPackageCreate] = Field(..., min_length=1)

    shipping_charge: float = Field(0, ge=0, description="Shipping charge to debit from wallet")

    gst_number: Optional[str] = Field(None, max_length=20)
    eway_bill_number: Optional[str] = Field(None, max_length=30)


# ── Order Response ─────────────────────────────────────────────────────────


class OrderOut(BaseModel):
    id: str
    order_number: str
    order_type: str
    pickup_address: PickupAddressOut
    consignee: ConsigneeOut
    payment_method: str
    cod_amount: Optional[float] = None
    to_pay_amount: Optional[float] = None
    rov: str
    order_value: float
    items: List[OrderItemOut]
    packages: List[OrderPackageOut]
    weight_summary: WeightSummary
    shipping_charge: float = 0
    gst_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    barcode: Optional[str] = None
    status: str
    created_by: str
    franchise_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: List[OrderOut]
    total: int
    page: int
    limit: int
    pages: int



class LocationRequest(BaseModel):
    lat: float
    lng: float

class OrderResponse(BaseModel):
    id: str
    order_number: str
    status: OrderStatus
    order_type: str
    payment_method: str
    order_value: float
    barcode: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True  


class OrderStatusListResponse(BaseModel):
    total: int
    status_filter: Optional[OrderStatus]
    data: List[OrderResponse]
# ── Bulk Order Create ─────────────────────────────────────────────────────


class BulkOrderCreate(BaseModel):
    orders: List[OrderCreate] = Field(..., min_length=1, max_length=50, description="List of orders to create (max 50)")


class BulkOrderError(BaseModel):
    index: int
    error: str


class BulkOrderResponse(BaseModel):
    total_submitted: int
    successful: int
    failed: int
    orders: List[OrderOut]
    errors: List[BulkOrderError]


class TodayStatusRequest(BaseModel):
     date: date                 
     
         
class FilterableStatus(str, Enum):
    DISPATCHED = "Dispatched"
    PICKED = "Picked"
    CANCELLED = "Cancelled"
    DELIVERED = "Delivered"

class OrderStatusRequest(BaseModel):
    status: FilterableStatus
    page: int = 1
    limit: int = 10