from app.modules.rate_calculator.schemas.rate_calculator import PaymentMode, RiskType, ShipmentType


def calculate_base_freight(base_price: float, chargeable_weight: float, price_per_kg: float) -> float:
    return round(base_price + (chargeable_weight * price_per_kg), 2)


def calculate_fuel_surcharge(base_freight: float, fuel_surcharge_percent: float) -> float:
    return round((base_freight * fuel_surcharge_percent) / 100, 2)


def calculate_insurance_charge(declared_value: float, insurance_percent: float, risk_type: RiskType) -> float:
    if risk_type != RiskType.CARRIER_RISK:
        return 0.0
    return round((declared_value * insurance_percent) / 100, 2)


def calculate_cod_charge(configured_cod_charge: float, payment_mode: PaymentMode) -> float:
    return round(configured_cod_charge, 2) if payment_mode == PaymentMode.COD else 0.0


def calculate_reverse_charge(configured_reverse_charge: float, shipment_type: ShipmentType) -> float:
    return round(configured_reverse_charge, 2) if shipment_type == ShipmentType.REVERSE else 0.0


def calculate_gst(subtotal: float, gst_percent: float) -> float:
    return round((subtotal * gst_percent) / 100, 2)
