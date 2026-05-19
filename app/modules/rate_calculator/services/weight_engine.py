import logging
from dataclasses import dataclass

from app.modules.rate_calculator.schemas.rate_calculator import RateCalculationRequest
from app.modules.rate_calculator.utils.volumetric import DEFAULT_VOLUMETRIC_DIVISOR, calculate_volumetric_weight

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeightSummary:
    physical_weight: float
    volumetric_weight: float
    chargeable_weight: float


class WeightEngine:
    def calculate(self, payload: RateCalculationRequest, divisor: float = DEFAULT_VOLUMETRIC_DIVISOR) -> WeightSummary:
        total_physical = 0.0
        total_volumetric = 0.0

        for package in payload.packages:
            row_physical = package.physical_weight * package.count
            row_volumetric = calculate_volumetric_weight(
                length=package.length,
                breadth=package.breadth,
                height=package.height,
                count=package.count,
                divisor=divisor,
            )
            logger.info(
                "Volumetric row calculated count=%s physical=%s volumetric=%s divisor=%s",
                package.count,
                row_physical,
                row_volumetric,
                divisor,
            )
            total_physical += row_physical
            total_volumetric += row_volumetric

        return WeightSummary(
            physical_weight=round(total_physical, 2),
            volumetric_weight=round(total_volumetric, 2),
            chargeable_weight=round(max(total_physical, total_volumetric), 2),
        )
