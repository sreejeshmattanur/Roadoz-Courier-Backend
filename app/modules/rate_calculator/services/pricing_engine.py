import logging

from app.modules.rate_calculator.models.pricing_rule import PricingRule
from app.modules.rate_calculator.schemas.rate_calculator import PricingBreakdown, RateCalculationRequest
from app.modules.rate_calculator.services.weight_engine import WeightSummary
from app.modules.rate_calculator.utils.pricing_helpers import (
    calculate_base_freight,
    calculate_cod_charge,
    calculate_fuel_surcharge,
    calculate_gst,
    calculate_insurance_charge,
    calculate_reverse_charge,
)

logger = logging.getLogger(__name__)


class PricingEngine:
    def calculate(
        self,
        payload: RateCalculationRequest,
        weights: WeightSummary,
        rule: PricingRule,
    ) -> PricingBreakdown:
        base_freight = calculate_base_freight(
            base_price=float(rule.base_price),
            chargeable_weight=weights.chargeable_weight,
            price_per_kg=float(rule.price_per_kg),
        )
        reverse_charge = calculate_reverse_charge(float(rule.reverse_charge), payload.shipment_type)
        cod_charge = calculate_cod_charge(float(rule.cod_charge), payload.payment_mode)
        fuel_charge = calculate_fuel_surcharge(base_freight, float(rule.fuel_surcharge_percent))
        insurance_charge = calculate_insurance_charge(
            declared_value=payload.declared_value,
            insurance_percent=float(rule.insurance_percent),
            risk_type=payload.risk_type,
        )
        subtotal = round(base_freight + reverse_charge + cod_charge + fuel_charge + insurance_charge, 2)
        gst = calculate_gst(subtotal, float(rule.gst_percent))
        final_amount = round(subtotal + gst, 2)

        breakdown = PricingBreakdown(
            base_freight=base_freight,
            reverse_charge=reverse_charge,
            cod_charge=cod_charge,
            fuel_surcharge=fuel_charge,
            insurance_charge=insurance_charge,
            gst=gst,
            final_amount=final_amount,
        )
        logger.info("Pricing breakdown generated: %s", breakdown.model_dump())
        return breakdown
