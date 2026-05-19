from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.rate_calculator import PincodeServiceability, RateZone

async def determine_zone(db: AsyncSession, pickup: PincodeServiceability, delivery: PincodeServiceability) -> str:
    """
    Determines the pricing zone based on pickup and delivery pincodes/states.
    For demonstration: 
    - WITHIN_STATE if same state
    - Consults rate_zones table for specific zone mapping
    - Defaults to NATIONAL
    """
    if pickup.state.lower() == delivery.state.lower():
        return "WITHIN_STATE"
    
    # Check rate_zones mapping
    result = await db.execute(select(RateZone))
    zones = result.scalars().all()
    
    for zone in zones:
        states = [s.strip().lower() for s in zone.state_mapping.split(",")]
        if delivery.state.lower() in states:
            return zone.zone_name
            
    return "NATIONAL"
