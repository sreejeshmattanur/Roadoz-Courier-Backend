from pydantic import BaseModel
from typing import Dict, Optional

class DashboardAnalyticsResponse(BaseModel):
    total_orders: int
    rto_orders: int
    total_revenue_or_spend: float  # Represents Revenue for Super Admin, Spend for Franchise
    wallet_transactions_count: int
    
    cod_vs_prepaid: Dict[str, int]
    order_statuses: Dict[str, int]
    delivered_vs_rto: Dict[str, int]
    statewise_orders: Dict[str, int]
    
    extra_counts: Optional[Dict[str, float]] = None  # E.g. {"total_users": 10, "total_franchises": 2, "total_wallet_balance": 1500.0}
