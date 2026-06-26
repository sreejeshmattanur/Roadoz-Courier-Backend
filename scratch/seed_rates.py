import asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.rate_master import RateMaster

async def seed_rates():
    rates = [
        # Surface - Kerala within State
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 0.5, "base_rate": 104},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 1.0, "base_rate": 156},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 2.0, "base_rate": 234},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 3.0, "base_rate": 312},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 5.0, "base_rate": 455},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 10.0, "base_rate": 845},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 15.0, "base_rate": 1235},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 20.0, "base_rate": 1625},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 25.0, "base_rate": 2015},
        {"service_type": "Surface", "zone": "Kerala within State", "weight_up_to": 30.0, "base_rate": 2405},

        # Surface - South India
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 0.5, "base_rate": 130},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 1.0, "base_rate": 195},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 2.0, "base_rate": 312},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 3.0, "base_rate": 416},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 5.0, "base_rate": 624},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 10.0, "base_rate": 1170},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 15.0, "base_rate": 1755},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 20.0, "base_rate": 2340},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 25.0, "base_rate": 2925},
        {"service_type": "Surface", "zone": "South India", "weight_up_to": 30.0, "base_rate": 3510},

        # Surface - Rest of India
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 0.5, "base_rate": 156},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 1.0, "base_rate": 234},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 2.0, "base_rate": 390},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 3.0, "base_rate": 546},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 5.0, "base_rate": 845},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 10.0, "base_rate": 1690},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 15.0, "base_rate": 2470},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 20.0, "base_rate": 3250},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 25.0, "base_rate": 4030},
        {"service_type": "Surface", "zone": "Rest of India", "weight_up_to": 30.0, "base_rate": 4810},

        # Express - South India Express
        {"service_type": "Express", "zone": "South India Express", "weight_up_to": 1.0, "base_rate": 234},
        {"service_type": "Express", "zone": "South India Express", "weight_up_to": 5.0, "base_rate": 845},
        {"service_type": "Express", "zone": "South India Express", "weight_up_to": 10.0, "base_rate": 1625},
        {"service_type": "Express", "zone": "South India Express", "weight_up_to": 20.0, "base_rate": 3055},
        {"service_type": "Express", "zone": "South India Express", "weight_up_to": 30.0, "base_rate": 4420},

        # Express - All India Express
        {"service_type": "Express", "zone": "All India Express", "weight_up_to": 1.0, "base_rate": 325},
        {"service_type": "Express", "zone": "All India Express", "weight_up_to": 5.0, "base_rate": 1235},
        {"service_type": "Express", "zone": "All India Express", "weight_up_to": 10.0, "base_rate": 2405},
        {"service_type": "Express", "zone": "All India Express", "weight_up_to": 20.0, "base_rate": 4550},
        {"service_type": "Express", "zone": "All India Express", "weight_up_to": 30.0, "base_rate": 6500},
    ]

    async with AsyncSessionLocal() as db:
        await db.execute(delete(RateMaster))
        for rate in rates:
            rm = RateMaster(**rate)
            db.add(rm)
        await db.commit()
        print("Successfully seeded RateMaster table!")

if __name__ == "__main__":
    asyncio.run(seed_rates())
