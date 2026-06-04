import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rate_calculator.repositories.pricing_repository import PricingRepository
from app.modules.rate_calculator.schemas.rate_calculator import (
    RateCalculationData,
    RateCalculationRequest,
    RateCalculationResponse,
    PricingBreakdown,
)
from app.modules.rate_calculator.services.pricing_engine import PricingEngine
from app.modules.rate_calculator.services.weight_engine import WeightEngine
from app.modules.rate_calculator.utils.validators import validate_calculation_request
from app.services.rate_calculator.pincode_service import get_pincode_details

logger = logging.getLogger(__name__)


class RateCalculatorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.pricing_repository = PricingRepository(db)
        self.weight_engine = WeightEngine()
        self.pricing_engine = PricingEngine()

    async def calculate(self, payload: RateCalculationRequest) -> RateCalculationResponse:
        logger.info("Incoming rate calculation payload: %s", payload.model_dump())
        validate_calculation_request(payload)

        pickup = await self._validate_serviceability(payload.pickup_pincode, "pickup")
        delivery = await self._validate_serviceability(payload.delivery_pincode, "delivery")
        logger.info(
            "Serviceability validated pickup=%s/%s delivery=%s/%s",
            pickup.city,
            pickup.state,
            delivery.city,
            delivery.state,
        )

        weights = self.weight_engine.calculate(payload, divisor=5000.0)
        
        zone = self._determine_zone(
            pickup.city, pickup.state, delivery.city, delivery.state
        )
        
        try:
            base_rate = self._get_slab_rate(weights.chargeable_weight, zone)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
            
        fuel_charge = round(base_rate * 0.52, 2)
        subtotal = round(base_rate + fuel_charge, 2)
        gst_amount = round(subtotal * 0.18, 2)
        final_amount = round(subtotal + gst_amount, 2)

        pricing = PricingBreakdown(
            base_freight=base_rate,
            reverse_charge=0.0,
            cod_charge=0.0,
            fuel_surcharge=fuel_charge,
            insurance_charge=0.0,
            gst=gst_amount,
            final_amount=final_amount,
        )

        return RateCalculationResponse(
            data=RateCalculationData(
                calculator_type=payload.calculator_type,
                physical_weight=weights.physical_weight,
                volumetric_weight=weights.volumetric_weight,
                chargeable_weight=weights.chargeable_weight,
                pricing=pricing,
            )
        )

    def _determine_zone(self, pickup_city: str, pickup_state: str, delivery_city: str, delivery_state: str) -> str:
        from app.constants.tariff_rates import SOUTH_INDIA_STATES
        
        p_city = (pickup_city or "").strip().lower()
        d_city = (delivery_city or "").strip().lower()
        p_state = (pickup_state or "").strip().lower()
        d_state = (delivery_state or "").strip().lower()

        if p_city == d_city and p_state == d_state and p_city != "":
            return "LOCAL"
        if p_state == "kerala" and d_state == "kerala":
            return "KERALA"
        if p_state in SOUTH_INDIA_STATES and d_state in SOUTH_INDIA_STATES:
            return "SOUTH_INDIA"
        return "REST_OF_INDIA"

    def _get_slab_rate(self, weight: float, zone: str) -> float:
        from app.constants.tariff_rates import TARIFF_RATES
        rates = TARIFF_RATES.get(zone, {})
        for slab_weight in sorted(rates.keys()):
            if weight <= slab_weight:
                return float(rates[slab_weight])
        raise ValueError("Weight exceeds 35 KG")

    async def _validate_serviceability(self, pincode: str, label: str):
        try:
            return await get_pincode_details(self.db, pincode)
        except HTTPException as exc:
            logger.warning("Failed %s pincode serviceability check pincode=%s detail=%s", label, pincode, exc.detail)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label.title()} pincode is not serviceable.",
            ) from exc


async def calculate_rate(db: AsyncSession, request: RateCalculationRequest) -> RateCalculationResponse:
    try:
        return await RateCalculatorService(db).calculate(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Internal rate calculation error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal calculation failure.",
        ) from exc
