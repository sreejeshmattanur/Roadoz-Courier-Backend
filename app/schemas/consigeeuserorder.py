from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class PickupAddressResponse(BaseModel):
    id: str
    nickname: str
    contact_name: str
    phone: str
    email: Optional[str]
    address_line_1: str
    address_line_2: Optional[str]
    pincode: str
    city: str
    state: str
    country: str
    active: bool
    is_primary: bool
    created_at: datetime
    updated_at: datetime

class ConsigneeResponse(BaseModel):
    id: str
    name: str
    mobile: str
    alternate_mobile: Optional[str]
    email: Optional[str]
    address_line_1: str
    address_line_2: Optional[str]
    pincode: str
    city: str
    state: str
    status: str
    created_at: datetime
    updated_at: datetime

class WarehouseAddressResponse(BaseModel):
    name: str
    pincode: str
    city: str

class FranchiseAddressResponse(BaseModel):
    name: str
    pincode: str
    city: str

class ItemResponse(BaseModel):
    id: str
    product_name: str
    sku: Optional[str]
    unit_price: float
    qty: int
    total: float

class PackageResponse(BaseModel):
    id: str
    count: int
    length_cm: float
    breadth_cm: float
    height_cm: float
    vol_weight_kg: float
    physical_weight_kg: float

class WeightSummaryResponse(BaseModel):
    applicable_weight_kg: float
    total_boxes: int
    total_weight_kg: float
    total_vol_weight_kg: float

class TrackingHistoryResponse(BaseModel):
    stage: str
    status: str
    pincode: str
    timestamp: datetime

class OrderListResponse(BaseModel):
    id: str
    order_number: str
    order_type: str
    status: str
    previous_status: Optional[str]
    payment_method: str
    cod_amount: Optional[float]
    to_pay_amount: Optional[float]
    order_value: float
    total_weight_kg: float
    total_vol_weight_kg: float
    applicable_weight_kg: float
    total_boxes: int
    shipping_charge: float
    gst_number: Optional[str]
    eway_bill_number: Optional[str]
    barcode: Optional[str]
    created_at: datetime
    updated_at: datetime
    pickup_address: Optional[PickupAddressResponse]
    consignee: Optional[ConsigneeResponse]
    warehouse_addresses: List[WarehouseAddressResponse]
    franchise_addresses: List[FranchiseAddressResponse]
    items: List[ItemResponse]
    packages: List[PackageResponse]
    weight_summary: WeightSummaryResponse
    tracking_history: List[TrackingHistoryResponse]

class PaginatedOrdersResponse(BaseModel):
    items: List[OrderListResponse]
    total: int
    page: int
    limit: int
    total_pages: int
