import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rate_calculator.repositories.pricing_repository import PricingRepository
from app.modules.rate_calculator.schemas.rate_calculator import (
    RateCalculationData,
    RateCalculationRequest,
    RateCalculationResponse,
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

        initial_weights = self.weight_engine.calculate(payload)
        rule = await self.pricing_repository.find_pricing_rule(payload, initial_weights.chargeable_weight)
        weights = self.weight_engine.calculate(payload, divisor=float(rule.volumetric_divisor))
        if weights.chargeable_weight != initial_weights.chargeable_weight:
            rule = await self.pricing_repository.find_pricing_rule(payload, weights.chargeable_weight)

        pricing = self.pricing_engine.calculate(payload, weights, rule)

        return RateCalculationResponse(
            data=RateCalculationData(
                calculator_type=payload.calculator_type,
                physical_weight=weights.physical_weight,
                volumetric_weight=weights.volumetric_weight,
                chargeable_weight=weights.chargeable_weight,
                pricing=pricing,
            )
        )

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
