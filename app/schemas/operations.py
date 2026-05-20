from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    franchise_id: Optional[str] = None
    expense_date: date
    expense_head: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    approved_by: Optional[str] = None
    remarks: Optional[str] = Field(None, max_length=500)


class ExpenseOut(BaseModel):
    id: str
    franchise_id: Optional[str]
    expense_date: date
    expense_head: str
    amount: float
    approved_by: Optional[str]
    remarks: Optional[str]
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CashVoucherCreate(BaseModel):
    franchise_id: Optional[str] = None
    voucher_date: date
    type: str = Field(..., pattern="^(debit|credit)$")
    amount: float = Field(..., gt=0)
    payment_mode: str = Field("Cash", max_length=30)
    description: str = Field(..., min_length=1, max_length=500)


class CashVoucherOut(BaseModel):
    id: str
    voucher_no: str
    franchise_id: Optional[str]
    voucher_date: date
    type: str
    amount: float
    payment_mode: str
    description: str
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AttendanceCreate(BaseModel):
    user_id: str
    franchise_id: Optional[str] = None
    attendance_date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: str = Field("present", pattern="^(present|absent|half_day|leave)$")
    remarks: Optional[str] = Field(None, max_length=500)


class AttendanceOut(BaseModel):
    id: str
    user_id: str
    franchise_id: Optional[str]
    attendance_date: date
    check_in: Optional[datetime]
    check_out: Optional[datetime]
    status: str
    remarks: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ManifestCreate(BaseModel):
    franchise_id: Optional[str] = None
    manifest_date: date
    vehicle_no: Optional[str] = Field(None, max_length=50)
    route: Optional[str] = Field(None, max_length=150)
    order_ids: List[str] = Field(..., min_length=1)


class ManifestOrderOut(BaseModel):
    id: str
    order_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ManifestOut(BaseModel):
    id: str
    manifest_no: str
    franchise_id: Optional[str]
    manifest_date: date
    vehicle_no: Optional[str]
    route: Optional[str]
    status: str
    created_by: str
    created_at: datetime
    orders: List[ManifestOrderOut] = []

    model_config = {"from_attributes": True}


class PodCreate(BaseModel):
    order_id: str
    receiver_name: str = Field(..., min_length=1, max_length=150)
    received_at: datetime
    delivery_staff_id: Optional[str] = None
    otp_verified: bool = False
    signature_url: Optional[str] = None
    remarks: Optional[str] = Field(None, max_length=500)


class PodOut(BaseModel):
    id: str
    order_id: str
    receiver_name: str
    received_at: datetime
    delivery_staff_id: Optional[str]
    otp_verified: bool
    signature_url: Optional[str]
    remarks: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
