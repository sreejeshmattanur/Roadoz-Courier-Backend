from typing import Optional

from pydantic import BaseModel


class WebConfigurationCreate(BaseModel):
    maintenance_mode: bool = False
    allow_order_create: bool = True
    allow_to_pay: bool = True
    app_timezone: str = "Asia/Kolkata"
    razorpay_key_id: Optional[str] = None
    razorpay_secret_key: Optional[str] = None


class WebConfigurationPatch(BaseModel):
    maintenance_mode: Optional[bool] = None
    allow_order_create: Optional[bool] = None
    allow_to_pay: Optional[bool] = None
    app_timezone: Optional[str] = None
    razorpay_key_id: Optional[str] = None
    razorpay_secret_key: Optional[str] = None