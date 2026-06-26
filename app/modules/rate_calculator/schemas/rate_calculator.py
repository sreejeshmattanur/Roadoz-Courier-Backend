from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class CalculatorType(str, Enum):
    B2C = "B2C"
    B2B = "B2B"

class ServiceType(str, Enum):
    SURFACE = "Surface"
    EXPRESS = "Express"
    INTERNATIONAL = "International"


class ShipmentType(str, Enum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


class PaymentMode(str, Enum):
    COD = "COD"
    PREPAID = "PREPAID"
    TO_PAY = "TO_PAY"
    CREDIT = "CREDIT"


class RiskType(str, Enum):
    OWNER_RISK = "OWNER_RISK"
    CARRIER_RISK = "CARRIER_RISK"


class RatePackageInput(BaseModel):
    count: int = Field(..., ge=0)
    length: float = Field(..., ge=0)
    breadth: float = Field(..., ge=0)
    height: float = Field(..., ge=0)
    physical_weight: float = Field(..., ge=0)


class RateCalculationRequest(BaseModel):
    calculator_type: CalculatorType
    service_type: ServiceType
    pickup_pincode: str = Field(..., min_length=6, max_length=10)
    delivery_pincode: str = Field(..., min_length=6, max_length=10)
    shipment_type: ShipmentType
    payment_mode: PaymentMode
    risk_type: RiskType
    declared_value: float = Field(0, ge=0)
    is_gst_exempt: bool = False
    packages: List[RatePackageInput] = Field(..., min_length=1)

    @field_validator("pickup_pincode", "delivery_pincode")
    @classmethod
    def validate_pincode(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("pincode must contain only digits")
        return cleaned


class PricingBreakdown(BaseModel):
    freight_charge: float
    freight_gst: float
    total_freight: float
    is_manual_freight: bool = False
    zone: str = ""
    applied_weight_slab: float = 0.0


class RateCalculationData(BaseModel):
    calculator_type: CalculatorType
    physical_weight: float
    volumetric_weight: float
    chargeable_weight: float
    pricing: PricingBreakdown


class RateCalculationResponse(BaseModel):
    success: bool = True
    data: RateCalculationData
