import logging

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rate_calculator.models.pricing_rule import PricingRule
from app.modules.rate_calculator.models.pricing_zone import PricingZone
from app.modules.rate_calculator.schemas.rate_calculator import RateCalculationRequest

logger = logging.getLogger(__name__)


class PricingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_zone(self, pickup_region: str, delivery_region: str) -> PricingZone | None:
        result = await self.db.execute(
            select(PricingZone).where(
                and_(
                    PricingZone.pickup_region == pickup_region,
                    PricingZone.delivery_region == delivery_region,
                )
            )
        )
        return result.scalar_one_or_none()

    async def find_pricing_rule(
        self,
        payload: RateCalculationRequest,
        chargeable_weight: float,
    ) -> PricingRule:
        logger.info(
            "Matching pricing slab calculator_type=%s shipment_type=%s payment_mode=%s risk_type=%s weight=%s",
            payload.calculator_type.value,
            payload.shipment_type.value,
            payload.payment_mode.value,
            payload.risk_type.value,
            chargeable_weight,
        )
        result = await self.db.execute(
            select(PricingRule).where(
                and_(
                    PricingRule.calculator_type == payload.calculator_type.value,
                    PricingRule.shipment_type == payload.shipment_type.value,
                    PricingRule.payment_mode == payload.payment_mode.value,
                    PricingRule.risk_type == payload.risk_type.value,
                    PricingRule.is_active.is_(True),
                    PricingRule.min_weight <= chargeable_weight,
                    PricingRule.max_weight >= chargeable_weight,
                )
            )
        )
        rules = result.scalars().all()
        if len(rules) > 1:
            logger.error("Conflicting pricing slabs matched: %s", [rule.id for rule in rules])
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Multiple active pricing slabs matched for this request.",
            )
        if not rules:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pricing slab not found for this shipment.",
            )
        return rules[0]
