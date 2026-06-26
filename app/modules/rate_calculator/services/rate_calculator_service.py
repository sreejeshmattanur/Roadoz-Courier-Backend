import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.modules.rate_calculator.schemas.rate_calculator import (
    RateCalculationData,
    RateCalculationRequest,
    RateCalculationResponse,
    PricingBreakdown,
)
from app.modules.rate_calculator.services.weight_engine import WeightEngine
from app.modules.rate_calculator.utils.validators import validate_calculation_request
from app.services.rate_calculator.pincode_service import get_pincode_details
from app.models.rate_master import RateMaster

logger = logging.getLogger(__name__)


class RateCalculatorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.weight_engine = WeightEngine()

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
            payload.service_type.value, pickup.state, delivery.state
        )
        
        if weights.chargeable_weight > 30.0:
            is_manual_freight = True
            base_rate = 0.0
            applied_slab = 0.0
        else:
            is_manual_freight = False
            rate_row = await self._get_rate_from_db(payload.service_type.value, zone, weights.chargeable_weight)
            if not rate_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No rate defined for Service: {payload.service_type.value}, Zone: {zone}, Weight: {weights.chargeable_weight}kg",
                )
            base_rate = float(rate_row.base_rate)
            applied_slab = float(rate_row.weight_up_to)
            
        if is_manual_freight:
            gst_amount = 0.0
            final_amount = 0.0
        else:
            if payload.is_gst_exempt:
                gst_amount = 0.0
            else:
                gst_amount = round(base_rate * 0.18, 2)
            final_amount = round(base_rate + gst_amount, 2)

        pricing = PricingBreakdown(
            freight_charge=base_rate,
            freight_gst=gst_amount,
            total_freight=final_amount,
            is_manual_freight=is_manual_freight,
            zone=zone,
            applied_weight_slab=applied_slab,
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

    def _determine_zone(self, service_type: str, pickup_state: str, delivery_state: str) -> str:
        from app.constants.tariff_rates import SOUTH_INDIA_STATES
        
        p_state = (pickup_state or "").strip().lower()
        d_state = (delivery_state or "").strip().lower()

        is_south_india = p_state in SOUTH_INDIA_STATES and d_state in SOUTH_INDIA_STATES
        is_kerala = p_state == "kerala" and d_state == "kerala"

        if service_type == "Surface":
            if is_kerala:
                return "Kerala within State"
            if is_south_india:
                return "South India"
            return "Rest of India"
        elif service_type == "Express":
            if is_south_india:
                return "South India Express"
            return "All India Express"
            
        return "Rest of India"

    async def _get_rate_from_db(self, service_type: str, zone: str, weight: float):
        result = await self.db.execute(
            select(RateMaster).where(
                and_(
                    RateMaster.service_type == service_type,
                    RateMaster.zone == zone,
                    RateMaster.weight_up_to >= weight
                )
            ).order_by(RateMaster.weight_up_to.asc()).limit(1)
        )
        return result.scalar_one_or_none()

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
