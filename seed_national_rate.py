import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.rate_calculator import RateCard, PincodeServiceability
import uuid

async def seed_data():
    async with AsyncSessionLocal() as db:
        # Check if pincode 500049 exists
        # To avoid unique constraint failures, we'll just merge
        pc1 = PincodeServiceability(pincode="500049", city="Secunderabad", state="Telangana", serviceable=True)
        pc2 = PincodeServiceability(pincode="110001", city="New Delhi", state="Delhi", serviceable=True)
        await db.merge(pc1)
        await db.merge(pc2)
        
        # Seed Rate Card for NATIONAL zone
        card = RateCard(
            id=str(uuid.uuid4()),
            customer_type="B2C",
            shipment_type="SURFACE",
            zone="NATIONAL",
            min_weight=0.0,
            max_weight=5.0,
            base_price=600.0, # Slightly higher base rate for national
            additional_kg_price=120.0,
            cod_charge=50.0,
            insurance_charge=0.0,
            appointment_charge=0.0,
            active=True
        )
        db.add(card)
        
        await db.commit()
        print("Successfully added missing pincodes and NATIONAL rate card!")

if __name__ == "__main__":
    asyncio.run(seed_data())
