DEFAULT_VOLUMETRIC_DIVISOR = 5000.0


def calculate_volumetric_weight(
    length: float,
    breadth: float,
    height: float,
    count: int = 1,
    divisor: float = DEFAULT_VOLUMETRIC_DIVISOR,
) -> float:
    if divisor <= 0:
        divisor = DEFAULT_VOLUMETRIC_DIVISOR
    return round((length * breadth * height * count) / divisor, 2)
