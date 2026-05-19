from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException
from app.models.rate_calculator import RateCard
import math

async def calculate_base_freight(
    db: AsyncSession, 
    customer_type: str, 
    shipment_type: str, 
    zone: str, 
    chargeable_weight: float
) -> tuple[float, RateCard]:
    """
    Finds the applicable rate card based on exact slab, or falls back to nearest slab and adds additional_kg_price.
    """
    result = await db.execute(
        select(RateCard).where(
            and_(
                RateCard.customer_type == customer_type,
                RateCard.shipment_type == shipment_type,
                RateCard.zone == zone,
                RateCard.active == True,
                RateCard.min_weight <= chargeable_weight,
                RateCard.max_weight >= chargeable_weight
            )
        )
    )
    card = result.scalar_one_or_none()
    
    if card:
        return float(card.base_price), card
        
    # Fallback to the maximum weight slab and calculate additional weight
    result = await db.execute(
        select(RateCard).where(
            and_(
                RateCard.customer_type == customer_type,
                RateCard.shipment_type == shipment_type,
                RateCard.zone == zone,
                RateCard.active == True
            )
        ).order_by(RateCard.max_weight.desc()).limit(1)
    )
    max_card = result.scalar_one_or_none()
    
    if not max_card:
        raise HTTPException(status_code=400, detail=f"No active rate card found for {customer_type} | {shipment_type} | {zone}")
    
    if chargeable_weight <= float(max_card.max_weight):
        # Should only happen if there is a gap in slabs
        raise HTTPException(status_code=400, detail="Pricing slab configuration error (weight gap)")
        
    # Additional logic: charge per additional KG
    extra_weight = math.ceil(chargeable_weight - float(max_card.max_weight))
    base_price = float(max_card.base_price) + (extra_weight * float(max_card.additional_kg_price))
    
    return base_price, max_card
