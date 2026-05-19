from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.rate_calculator import FuelConfig, GSTConfig

async def get_current_fuel_percentage(db: AsyncSession) -> float:
    result = await db.execute(
        select(FuelConfig).order_by(FuelConfig.effective_from.desc()).limit(1)
    )
    config = result.scalar_one_or_none()
    # Defaulting to 0.0 if not configured
    return float(config.percentage) if config else 0.0

async def get_current_gst_percentage(db: AsyncSession) -> float:
    result = await db.execute(select(GSTConfig).limit(1))
    config = result.scalar_one_or_none()
    # Defaulting to 18.0 if not configured
    return float(config.percentage) if config else 18.0
