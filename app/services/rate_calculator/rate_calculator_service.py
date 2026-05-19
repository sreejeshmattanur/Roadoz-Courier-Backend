from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.rate_calculator import RateCalculationRequest, RateCalculationResponse
from .volumetric_service import calculate_volumetric_weight, calculate_chargeable_weight
from .pincode_service import get_pincode_details
from .zone_service import determine_zone
from .pricing_service import calculate_base_freight
from .surcharge_service import get_current_fuel_percentage, get_current_gst_percentage

async def calculate_rate(db: AsyncSession, request: RateCalculationRequest) -> RateCalculationResponse:
    # 1. Pincode validation
    pickup = await get_pincode_details(db, request.pickup_pincode)
    delivery = await get_pincode_details(db, request.delivery_pincode)
    
    # 2. Zone determination
    zone = await determine_zone(db, pickup, delivery)
    
    # 3. Weight calculation (Multiple boxes)
    total_physical = 0.0
    total_chargeable = 0.0
    total_volumetric = 0.0
    
    for box in request.boxes:
        vol_weight = calculate_volumetric_weight(box, request.shipment_type)
        charge_weight = calculate_chargeable_weight(box.physical_weight, vol_weight)
        
        total_physical += box.physical_weight
        total_volumetric += vol_weight
        total_chargeable += charge_weight
        
    # 4. Base Rate calculation
    base_rate, rate_card = await calculate_base_freight(
        db, request.customer_type, request.shipment_type, zone, total_chargeable
    )
    
    # 5. Additional Charges (COD, Insurance, Appointment)
    additional_charges = 0.0
    if request.payment_mode.upper() == "COD":
        additional_charges += float(rate_card.cod_charge)
    if request.requires_insurance:
        # Insurance can be flat fee or percentage of declared value, keeping flat here based on rate card
        additional_charges += float(rate_card.insurance_charge)
    if request.requires_appointment:
        additional_charges += float(rate_card.appointment_charge)
        
    # 6. Fuel Surcharge
    fuel_percentage = await get_current_fuel_percentage(db)
    fuel_charge = round(base_rate * (fuel_percentage / 100), 2)
    
    # 7. Taxable Amount (Base + Fuel + Additional)
    taxable_amount = round(base_rate + fuel_charge + additional_charges, 2)
    
    # 8. GST (Applied on Taxable Amount)
    gst_percentage = await get_current_gst_percentage(db)
    gst_amount = round(taxable_amount * (gst_percentage / 100), 2)
    
    # 9. Final Amount
    final_amount = round(taxable_amount + gst_amount, 2)
    
    return RateCalculationResponse(
        zone=zone,
        physical_weight=round(total_physical, 2),
        volumetric_weight=round(total_volumetric, 2),
        chargeable_weight=round(total_chargeable, 2),
        base_rate=round(base_rate, 2),
        fuel_percentage=fuel_percentage,
        fuel_charge=fuel_charge,
        additional_charges=round(additional_charges, 2),
        taxable_amount=taxable_amount,
        gst_percentage=gst_percentage,
        gst_amount=gst_amount,
        final_amount=final_amount
    )
