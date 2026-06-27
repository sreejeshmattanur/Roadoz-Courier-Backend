from pydantic import BaseModel, Field, model_validator, computed_field
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

class ServiceType(str, Enum):
    SURFACE = "Surface"
    EXPRESS = "Express"
    INTERNATIONAL = "International"


class TodayStatusRequestDatewise(BaseModel):
    date: date
    status: str


class PaymentMethod(str, Enum):
    COD = "COD"
    PREPAID = "Prepaid"
    TO_PAY = "To Pay"
    CREDIT = "Credit"


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
    active: bool = Field(True, description="Whether this address is active")
    is_primary: bool = Field(False, description="Whether this is the primary pickup address")


class PickupAddressUpdate(BaseModel):
    nickname: Optional[str] = Field(None, min_length=1, max_length=100)
    contact_name: Optional[str] = Field(None, min_length=1, max_length=150)
    phone: Optional[str] = Field(None, min_length=1, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, min_length=1, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, min_length=1, max_length=10)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=1, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    active: Optional[bool] = None
    is_primary: Optional[bool] = None


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
    active: bool
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PickupAddressListResponse(BaseModel):
    items: List[PickupAddressOut]
    total: int
    page: int
    limit: int
    total_pages: int


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
    status: str = "active"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConsigneeListResponse(BaseModel):
    items: List[ConsigneeOut]
    total: int
    page: int
    limit: int
    pages: int


class ConsigneeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    mobile: Optional[str] = Field(None, min_length=1, max_length=20)
    alternate_mobile: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: Optional[str] = Field(None, min_length=1, max_length=500)
    address_line_2: Optional[str] = Field(None, max_length=500)
    pincode: Optional[str] = Field(None, min_length=1, max_length=10)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$", description="Must be 'active' or 'inactive'")


class ConsigneeStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|inactive)$", description="Must be 'active' or 'inactive'")


# ── Order Items (Product Details) ──────────────────────────────────────────


class OrderItemCreate(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=255)
    # sku: Optional[str] = Field(None, max_length=100)
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
    count: int = Field(0, ge=0, description="Number of boxes")
    length_cm: float = Field(..., ge=0)
    breadth_cm: float = Field(..., ge=0)
    height_cm: float = Field(..., ge=0)
    vol_weight_kg: float = Field(..., ge=0, description="Volumetric weight (B2C dividend 5000)")
    physical_weight_kg: float = Field(..., ge=0)


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
    warehouse_addresses_ids: Optional[List[str]] = []
    franchise_addresses_ids: Optional[List[str]] = []
    payment_method: PaymentMethod
    cod_amount: Optional[float] = Field(None, ge=0, description="Required when payment_method is COD")
    to_pay_amount: Optional[float] = Field(None, ge=0, description="Required when payment_method is To Pay")
    credit_amount: Optional[float] = Field(None, ge=0, description="Required when payment_method is Credit")
    rov: ROV

    order_value: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _validate_payment_amounts(self):
        if self.payment_method == PaymentMethod.COD and self.cod_amount is None:
            raise ValueError("cod_amount is required when payment_method is COD")
        if self.payment_method == PaymentMethod.TO_PAY and self.to_pay_amount is None:
            raise ValueError("to_pay_amount is required when payment_method is To Pay")
        if self.payment_method == PaymentMethod.CREDIT and self.credit_amount is None:
            raise ValueError("credit_amount is required when payment_method is Credit")
            
        if self.payment_method == PaymentMethod.COD:
            self.to_pay_amount = None
            self.credit_amount = None
        elif self.payment_method == PaymentMethod.TO_PAY:
            self.cod_amount = None
            self.credit_amount = None
        elif self.payment_method == PaymentMethod.CREDIT:
            self.cod_amount = None
            self.to_pay_amount = None
        elif self.payment_method == PaymentMethod.PREPAID:
            self.cod_amount = None
            self.to_pay_amount = None
            self.credit_amount = None
        return self

    items: List[OrderItemCreate] = Field(..., min_length=1)
    packages: List[OrderPackageCreate] = Field(..., min_length=1)

    service_type: ServiceType = Field(ServiceType.SURFACE)
    is_gst_exempt: Optional[bool] = Field(False, description="Optional GST exemption for users with orders:create permission")

    gst_number: Optional[str] = Field(None, max_length=20)
    eway_bill_number: Optional[str] = Field(None, max_length=30)
    insurance: float | None = 0
    regional_area: float | None = 0


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
    credit_amount: Optional[float] = None
    rov: str
    order_value: float
    items: List[OrderItemOut]
    packages: List[OrderPackageOut]
    weight_summary: WeightSummary
    service_type: str
    freight_charge: float = 0
    freight_gst: float = 0
    total_freight: float = 0
    applied_weight_slab: Optional[float] = None
    pricing_zone: Optional[str] = None
    is_manual_freight: bool = False
    manual_freight_reason: Optional[str] = None
    gst_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    insurance: float | None = None
    regional_area: float | None = None
    barcode: Optional[str] = None
    status: str
    created_by: str
    franchise_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def shipping_charge(self) -> float:
        return self.total_freight


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


class BulkOrderOut(BaseModel):
    id: str
    file_name: str
    order_type: str
    pickup_address_id: str
    status: str
    total_orders: int
    successful_orders: int
    failed_orders: int
    created_by: str
    franchise_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class BulkOrderListResponse(BaseModel):
    items: List[BulkOrderOut]
    total: int
    page: int
    limit: int
    pages: int

class BulkOrderError(BaseModel):
    index: int
    error: str

class BulkOrderResponse(BaseModel):
    bulk_order: BulkOrderOut
    errors: List[BulkOrderError]


class TodayStatusRequest(BaseModel):
    date: date   
    exact_status: Optional[str] = None
    search: Optional[str] = None             



class OrderUpdate(BaseModel):
    order_type: Optional[OrderType] = None

    pickup_address_id: Optional[str] = None
    consignee_id: Optional[str] = None
    warehouse_addresses_id: Optional[str] = None

    payment_method: Optional[PaymentMethod] = None

    cod_amount: Optional[float] = None
    to_pay_amount: Optional[float] = None
    credit_amount: Optional[float] = None

    rov: Optional[ROV] = None

    order_value: Optional[float] = None

    gst_number: Optional[str] = None
    eway_bill_number: Optional[str] = None

    service_type: Optional[ServiceType] = None
    is_gst_exempt: Optional[bool] = Field(None, description="Optional GST exemption for users with orders:create permission")
    total_freight: Optional[float] = None

    items: Optional[List[OrderItemCreate]] = None
    packages: Optional[List[OrderPackageCreate]] = None

     
         
class FilterableStatus(str, Enum):
    DISPATCHED = "Dispatched"
    PICKED = "Picked"
    CANCELLED = "Cancelled"
    DELIVERED = "Delivered"

class OrderStatusRequest(BaseModel):
    status: FilterableStatus
    page: int = 1
    limit: int = 10

class ManualFreightUpdate(BaseModel):
    freight_charge: float = Field(..., ge=0, description="Manual base freight charge")
    reason: Optional[str] = Field(None, description="Reason for manual freight entry")