from app.schemas.rate_calculator import BoxInput

def calculate_volumetric_weight(box: BoxInput, shipment_type: str) -> float:
    """
    Calculates volumetric weight for a single box.
    Surface shipment: (L * B * H) / 5000
    Air shipment: (L * B * H) / 4000
    """
    volume = box.length * box.breadth * box.height
    divisor = 4000 if shipment_type.upper() == "AIR" else 5000
    return round(volume / divisor, 2)

def calculate_chargeable_weight(physical_weight: float, volumetric_weight: float) -> float:
    """
    Chargeable weight is MAX(Physical, Volumetric).
    """
    return round(max(physical_weight, volumetric_weight), 2)
