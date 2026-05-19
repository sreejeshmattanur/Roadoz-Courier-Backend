import logging

from fastapi import HTTPException, status

from app.modules.rate_calculator.schemas.rate_calculator import CalculatorType, RateCalculationRequest

logger = logging.getLogger(__name__)


def validate_calculation_request(payload: RateCalculationRequest) -> None:
    if payload.calculator_type == CalculatorType.B2C and len(payload.packages) != 1:
        logger.warning("Failed rate calculation validation: B2C package count=%s", len(payload.packages))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="B2C rate calculation supports exactly one package.",
        )

    if payload.calculator_type == CalculatorType.B2B and not payload.packages:
        logger.warning("Failed rate calculation validation: B2B package list is empty")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="B2B rate calculation requires at least one package.",
        )
