import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.rate_calculator import RateCard
import uuid

async def seed_data():
    async with AsyncSessionLocal() as db:
        # B2B South Zone
        b2b_south = RateCard(
            id=str(uuid.uuid4()),
            customer_type="B2B",
            shipment_type="SURFACE",
            zone="SOUTH_ZONE",
            min_weight=0.0,
            max_weight=5.0,
            base_price=400.0,  # B2B is usually cheaper than B2C
            additional_kg_price=80.0,
            cod_charge=50.0,
            insurance_charge=0.0,
            appointment_charge=0.0,
            active=True
        )
        # B2B National
        b2b_national = RateCard(
            id=str(uuid.uuid4()),
            customer_type="B2B",
            shipment_type="SURFACE",
            zone="NATIONAL",
            min_weight=0.0,
            max_weight=5.0,
            base_price=550.0,
            additional_kg_price=100.0,
            cod_charge=50.0,
            insurance_charge=0.0,
            appointment_charge=0.0,
            active=True
        )
        db.add_all([b2b_south, b2b_national])
        await db.commit()
        print("Successfully added B2B rate cards!")

if __name__ == "__main__":
    asyncio.run(seed_data())
