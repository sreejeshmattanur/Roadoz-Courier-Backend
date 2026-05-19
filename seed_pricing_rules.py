import asyncio
import uuid
from itertools import product

from sqlalchemy import and_, select

from app.core.database import AsyncSessionLocal, init_db
from app.modules.rate_calculator.models.pricing_rule import PricingRule


CALCULATOR_TYPES = ("B2C", "B2B")
SHIPMENT_TYPES = ("FORWARD", "REVERSE")
PAYMENT_MODES = ("COD", "PREPAID", "TO_PAY")
RISK_TYPES = ("OWNER_RISK", "CARRIER_RISK")


def _rule_amounts(calculator_type: str, shipment_type: str, payment_mode: str, risk_type: str) -> dict:
    is_b2b = calculator_type == "B2B"
    return {
        "base_price": 250.0 if is_b2b else 80.0,
        "price_per_kg": 25.0 if is_b2b else 40.0,
        "cod_charge": 50.0 if payment_mode == "COD" else 0.0,
        "reverse_charge": 75.0 if shipment_type == "REVERSE" else 0.0,
        "fuel_surcharge_percent": 10.0,
        "insurance_percent": 1.0 if risk_type == "CARRIER_RISK" else 0.0,
        "gst_percent": 18.0,
        "volumetric_divisor": 5000.0,
        "max_weight": 500.0 if is_b2b else 50.0,
    }


async def seed_pricing_rules() -> None:
    await init_db()
    created = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        for calculator_type, shipment_type, payment_mode, risk_type in product(
            CALCULATOR_TYPES,
            SHIPMENT_TYPES,
            PAYMENT_MODES,
            RISK_TYPES,
        ):
            existing = await db.execute(
                select(PricingRule).where(
                    and_(
                        PricingRule.calculator_type == calculator_type,
                        PricingRule.shipment_type == shipment_type,
                        PricingRule.payment_mode == payment_mode,
                        PricingRule.risk_type == risk_type,
                        PricingRule.min_weight == 0,
                        PricingRule.is_active.is_(True),
                    )
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            amounts = _rule_amounts(calculator_type, shipment_type, payment_mode, risk_type)
            db.add(
                PricingRule(
                    id=str(uuid.uuid4()),
                    calculator_type=calculator_type,
                    shipment_type=shipment_type,
                    payment_mode=payment_mode,
                    risk_type=risk_type,
                    min_weight=0,
                    max_weight=amounts["max_weight"],
                    base_price=amounts["base_price"],
                    price_per_kg=amounts["price_per_kg"],
                    cod_charge=amounts["cod_charge"],
                    reverse_charge=amounts["reverse_charge"],
                    fuel_surcharge_percent=amounts["fuel_surcharge_percent"],
                    insurance_percent=amounts["insurance_percent"],
                    gst_percent=amounts["gst_percent"],
                    volumetric_divisor=amounts["volumetric_divisor"],
                    is_active=True,
                )
            )
            created += 1

        await db.commit()

    print(f"Pricing rules seeded. created={created}, skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(seed_pricing_rules())
