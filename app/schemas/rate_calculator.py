from pydantic import BaseModel, Field
from typing import List, Optional

class BoxInput(BaseModel):
    length: float = Field(..., gt=0, description="Length in cm")
    breadth: float = Field(..., gt=0, description="Breadth in cm")
    height: float = Field(..., gt=0, description="Height in cm")
    physical_weight: float = Field(..., gt=0, description="Weight in kg")

class RateCalculationRequest(BaseModel):
    pickup_pincode: str = Field(..., min_length=6, max_length=10)
    delivery_pincode: str = Field(..., min_length=6, max_length=10)
    shipment_type: str = Field(..., description="e.g. SURFACE or AIR")
    payment_mode: str = Field(..., description="e.g. PREPAID or COD")
    declared_value: float = Field(0.0, ge=0)
    customer_type: str = Field("B2C", description="e.g. B2B or B2C")
    boxes: List[BoxInput] = Field(..., min_length=1)
    requires_appointment: bool = Field(False)
    requires_insurance: bool = Field(False)

class RateCalculationResponse(BaseModel):
    zone: str
    physical_weight: float
    volumetric_weight: float
    chargeable_weight: float
    base_rate: float
    fuel_percentage: float
    fuel_charge: float
    additional_charges: float
    taxable_amount: float
    gst_percentage: float
    gst_amount: float
    final_amount: float

class RateCardBase(BaseModel):
    customer_type: str
    shipment_type: str
    zone: str
    min_weight: float
    max_weight: float
    base_price: float
    additional_kg_price: float = 0.0
    cod_charge: float = 0.0
    insurance_charge: float = 0.0
    appointment_charge: float = 0.0
    active: bool = True

class RateCardCreate(RateCardBase):
    pass

class RateCardUpdate(RateCardBase):
    customer_type: Optional[str] = None
    shipment_type: Optional[str] = None
    zone: Optional[str] = None
    min_weight: Optional[float] = None
    max_weight: Optional[float] = None
    base_price: Optional[float] = None

class RateCardOut(RateCardBase):
    id: str

    model_config = {"from_attributes": True}
