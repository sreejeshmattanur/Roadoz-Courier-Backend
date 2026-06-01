from typing import Optional,List
from pydantic import BaseModel
from datetime import datetime, date



class RevenueRequest(BaseModel):
    start_date: date
    end_date: date
    status: Optional[str] = None  # Optional: filter by specific status
    payment_method: Optional[str] = None  # Optional: filter by payment method (COD/Prepaid/To Pay)

class DailyRevenueResponse(BaseModel):
    date: str
    total_orders: int
    total_revenue: float
    total_cod_amount: float
    total_prepaid_amount: float
    total_to_pay_amount: float
    orders_by_status: dict

class RevenueSummaryResponse(BaseModel):
    success: bool
    period: dict
    total_revenue: float
    total_orders: int
    average_order_value: float
    revenue_by_payment_method: dict
    revenue_by_status: dict
    daily_breakdown: List[DailyRevenueResponse]
    user_role: str
    generated_at: str


# ============= Helper Functions =============
