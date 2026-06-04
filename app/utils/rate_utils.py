def reverse_calculate_charges(shipping_charge: float) -> dict:
    """
    Reverse calculates base freight, fuel charge, and GST from a total shipping charge
    based on fixed percentages: 52% Fuel Surcharge, 18% GST.
    Total = Base * 1.52 * 1.18
    """
    if not shipping_charge or shipping_charge <= 0:
        return {
            "base_freight": 0.0,
            "fuel_surcharge": 0.0,
            "gst_amount": 0.0
        }
    
    subtotal = round(shipping_charge / 1.18, 2)
    gst_amount = round(shipping_charge - subtotal, 2)
    
    base_freight = round(subtotal / 1.52, 2)
    fuel_surcharge = round(subtotal - base_freight, 2)
    
    return {
        "base_freight": base_freight,
        "fuel_surcharge": fuel_surcharge,
        "gst_amount": gst_amount
    }
