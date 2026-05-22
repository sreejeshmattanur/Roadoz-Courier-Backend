from pydantic import BaseModel
from typing import Dict, Optional
from typing import List

class PaginationSchema(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class FranchiseOrderSchema(BaseModel):
    franchise_name: str
    order_count: int

class FranchiseOrdersDataSchema(BaseModel):
    pagination: PaginationSchema
    franchise_orders_data: List[FranchiseOrderSchema]
    

class DashboardAnalyticsResponse(BaseModel):
    total_orders: int
    rto_orders: int
    total_revenue_or_spend: float  # Represents Revenue for Super Admin, Spend for Franchise
    wallet_transactions_count: int
    
    cod_vs_prepaid: Dict[str, int]
    order_statuses: Dict[str, int]
    delivered_vs_rto: Dict[str, int]
    statewise_orders: Dict[str, int]
    
    # Financial and Operations Analytics
    total_expenses: Optional[float] = 0.0
    total_vouchers: Optional[int] = 0
    voucher_debit_sum: Optional[float] = 0.0
    voucher_credit_sum: Optional[float] = 0.0
    staff_attendance_present_count: Optional[int] = 0
    remittance_pending_sum: Optional[float] = 0.0
    remittance_remitted_sum: Optional[float] = 0.0
    
    franchise_orders_data: FranchiseOrdersDataSchema
    extra_counts: Optional[Dict[str, float]] = None  # E.g. {"total_users": 10, "total_franchises": 2, "total_wallet_balance": 1500.0}
