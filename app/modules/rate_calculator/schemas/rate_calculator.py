from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class CalculatorType(str, Enum):
    B2C = "B2C"
    B2B = "B2B"


class ShipmentType(str, Enum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


class PaymentMode(str, Enum):
    COD = "COD"
    PREPAID = "PREPAID"
    TO_PAY = "TO_PAY"


class RiskType(str, Enum):
    OWNER_RISK = "OWNER_RISK"
    CARRIER_RISK = "CARRIER_RISK"


class RatePackageInput(BaseModel):
    count: int = Field(..., ge=1)
    length: float = Field(..., gt=0)
    breadth: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    physical_weight: float = Field(..., gt=0)


class RateCalculationRequest(BaseModel):
    calculator_type: CalculatorType
    pickup_pincode: str = Field(..., min_length=6, max_length=10)
    delivery_pincode: str = Field(..., min_length=6, max_length=10)
    shipment_type: ShipmentType
    payment_mode: PaymentMode
    risk_type: RiskType
    declared_value: float = Field(0, ge=0)
    packages: List[RatePackageInput] = Field(..., min_length=1)

    @field_validator("pickup_pincode", "delivery_pincode")
    @classmethod
    def validate_pincode(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError("pincode must contain only digits")
        return cleaned


class PricingBreakdown(BaseModel):
    base_freight: float
    reverse_charge: float
    cod_charge: float
    fuel_surcharge: float
    insurance_charge: float
    gst: float
    final_amount: float


class RateCalculationData(BaseModel):
    calculator_type: CalculatorType
    physical_weight: float
    volumetric_weight: float
    chargeable_weight: float
    pricing: PricingBreakdown


class RateCalculationResponse(BaseModel):
    success: bool = True
    data: RateCalculationData
