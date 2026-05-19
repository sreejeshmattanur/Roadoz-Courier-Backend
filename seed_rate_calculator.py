import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.rate_calculator import RateZone, RateCard, FuelConfig, GSTConfig, PincodeServiceability
import uuid

async def seed_data():
    async with AsyncSessionLocal() as db:
        # Seed Fuel
        fuel = FuelConfig(id=str(uuid.uuid4()), percentage=52.0)
        db.add(fuel)
        
        # Seed GST
        gst = GSTConfig(id=str(uuid.uuid4()), percentage=18.0)
        db.add(gst)
        
        # Seed Zone
        zone1 = RateZone(id=str(uuid.uuid4()), zone_name="SOUTH_ZONE", state_mapping="Kerala,Tamil Nadu,Karnataka,Andhra Pradesh,Telangana")
        db.add(zone1)
        
        # Seed Pincodes
        pc1 = PincodeServiceability(pincode="682001", city="Kochi", state="Kerala", serviceable=True)
        pc2 = PincodeServiceability(pincode="600001", city="Chennai", state="Tamil Nadu", serviceable=True)
        db.add_all([pc1, pc2])
        
        # Seed Rate Card
        card = RateCard(
            id=str(uuid.uuid4()),
            customer_type="B2C",
            shipment_type="SURFACE",
            zone="SOUTH_ZONE",
            min_weight=0.0,
            max_weight=5.0,
            base_price=480.0,
            additional_kg_price=100.0,
            cod_charge=50.0,
            insurance_charge=0.0,
            appointment_charge=0.0,
            active=True
        )
        db.add(card)
        
        await db.commit()
        print("Successfully seeded rate calculator data!")

if __name__ == "__main__":
    asyncio.run(seed_data())
