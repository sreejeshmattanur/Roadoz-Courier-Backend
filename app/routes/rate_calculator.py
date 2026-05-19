from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.schemas.rate_calculator import (
    RateCalculationRequest, 
    RateCalculationResponse, 
    RateCardCreate, 
    RateCardUpdate, 
    RateCardOut
)
from app.services.rate_calculator.rate_calculator_service import calculate_rate
from app.models.rate_calculator import RateCard

router = APIRouter(tags=["Rate Calculator"])

@router.post("/rate-calculator/calculate", response_model=RateCalculationResponse)
async def calculate_courier_rate(request: RateCalculationRequest, db: AsyncSession = Depends(get_db)):
    """Calculate the comprehensive courier rate for a shipment."""
    return await calculate_rate(db, request)

@router.get("/rate-cards", response_model=List[RateCardOut])
async def list_rate_cards(db: AsyncSession = Depends(get_db)):
    """List all available rate cards."""
    result = await db.execute(select(RateCard))
    return result.scalars().all()

@router.post("/rate-cards", response_model=RateCardOut, status_code=201)
async def create_rate_card(data: RateCardCreate, db: AsyncSession = Depends(get_db)):
    """Create a new rate card."""
    card = RateCard(**data.model_dump())
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card

@router.put("/rate-cards/{card_id}", response_model=RateCardOut)
async def update_rate_card(card_id: str, data: RateCardUpdate, db: AsyncSession = Depends(get_db)):
    """Update an existing rate card."""
    result = await db.execute(select(RateCard).where(RateCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Rate card not found")
        
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(card, key, value)
        
    await db.commit()
    await db.refresh(card)
    return card

@router.delete("/rate-cards/{card_id}", status_code=204)
async def delete_rate_card(card_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a rate card."""
    result = await db.execute(select(RateCard).where(RateCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Rate card not found")
        
    await db.delete(card)
    await db.commit()
