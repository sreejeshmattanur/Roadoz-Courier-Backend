from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.rate_calculator.schemas.rate_calculator import RateCalculationRequest, RateCalculationResponse
from app.modules.rate_calculator.services.rate_calculator_service import calculate_rate

router = APIRouter(prefix="/rate-calculator", tags=["Rate Calculator"])


@router.post("/calculate", response_model=RateCalculationResponse)
async def calculate_courier_rate(
    request: RateCalculationRequest,
    db: AsyncSession = Depends(get_db),
):
    return await calculate_rate(db, request)
