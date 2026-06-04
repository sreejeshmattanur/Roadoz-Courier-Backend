from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from app.schemas.order import PickupAddressOut, ConsigneeOut


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"


# ── Invoice Order detail ─────────────────────────────────────────────────


class InvoiceOrderDetails(BaseModel):
    id: str
    order_number: str
    order_type: str
    payment_method: str
    order_value: float
    shipping_charge: float
    status: str
    created_at: datetime
    pickup_address: PickupAddressOut
    consignee: ConsigneeOut

    model_config = {"from_attributes": True}


class InvoiceOrderOut(BaseModel):
    id: str
    order_id: str
    shipping_charge: float
    created_at: datetime
    order: InvoiceOrderDetails

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def base_freight(self) -> float:
        from app.utils.rate_utils import reverse_calculate_charges
        return reverse_calculate_charges(self.shipping_charge)["base_freight"]

    @computed_field
    @property
    def fuel_surcharge(self) -> float:
        from app.utils.rate_utils import reverse_calculate_charges
        return reverse_calculate_charges(self.shipping_charge)["fuel_surcharge"]

    @computed_field
    @property
    def gst_amount(self) -> float:
        from app.utils.rate_utils import reverse_calculate_charges
        return reverse_calculate_charges(self.shipping_charge)["gst_amount"]


# ── Invoice ──────────────────────────────────────────────────────────────


class InvoiceOut(BaseModel):
    id: str
    invoice_number: str
    franchise_id: str
    description: str
    period_start: date
    period_end: date
    subtotal: float
    tax_rate: float
    tax_amount: float
    total_amount: float
    orders_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    invoice_orders: List[InvoiceOrderOut] = []

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    items: List[InvoiceOut]
    total: int
    page: int
    limit: int
    pages: int


# ── Requests ─────────────────────────────────────────────────────────────


class InvoiceGenerateRequest(BaseModel):
    franchise_id: str = Field(..., description="Franchise to generate invoice for")
    period_start: date = Field(..., description="Billing period start date")
    period_end: date = Field(..., description="Billing period end date")
    description: Optional[str] = Field(None, max_length=500, description="Custom description")
    tax_rate: float = Field(18.0, ge=0, le=100, description="Tax rate percentage (default 18%)")


class InvoiceMarkPaidRequest(BaseModel):
    remarks: Optional[str] = Field(None, max_length=500)
