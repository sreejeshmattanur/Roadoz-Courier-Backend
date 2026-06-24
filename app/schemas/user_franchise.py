from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class FranchiseApplicationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"

# ── Franchise Application Create ──────────────────────────────────────────

# class FranchiseApplicationCreate(BaseModel):
#     full_name: str = Field(..., max_length=100)
#     email: EmailStr
#     phone: str = Field(..., max_length=20)
#     date_of_birth: Optional[date] = None
#     gender: Optional[str] = Field(None, max_length=20)
#     current_address: Optional[str] = Field(None, max_length=500)
#     permanent_address: Optional[str] = Field(None, max_length=500)
    
#     proposed_location: Optional[str] = Field(None, max_length=255)
#     ownership_type: Optional[str] = Field(None, max_length=20)
#     detailed_business_address: Optional[str] = Field(None, max_length=500)
#     prior_experience: Optional[str] = Field(None, max_length=500)
#     years_active: Optional[int] = None
    
#     office_space_sqft: Optional[int] = None
#     office_ownership: Optional[str] = Field(None, max_length=20)
#     staff_count: Optional[int] = None
#     internet_availability: bool = False
#     computer_laptop: bool = False
    
#     investment_capacity: Optional[str] = Field(None, max_length=100)
#     source_of_funds: Optional[str] = Field(None, max_length=255)
#     bank_name: Optional[str] = Field(None, max_length=255)
#     account_number: Optional[str] = Field(None, max_length=50)
#     existing_loans: bool = False
#     existing_loan_details: Optional[str] = Field(None, max_length=1000)
    
#     preferred_service_area: Optional[str] = Field(None, max_length=255)
#     nearby_landmark: Optional[str] = Field(None, max_length=255)
#     pincode: str = Field(..., max_length=6)
    
#     doc_id_proof: bool = False
#     doc_address_proof: bool = False
#     doc_photographs: bool = False
#     doc_business_registration: bool = False
#     doc_bank_statement: bool = False
    
#     agree_to_terms: bool = False
#     submission_place: Optional[str] = Field(None, max_length=255)
#     submission_date: Optional[date] = None

class FranchiseApplicationResponse(BaseModel):
    id: str
    status: str
    full_name: str
    email: str
    phone: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    proposed_location: Optional[str] = None
    ownership_type: Optional[str] = None
    detailed_business_address: Optional[str] = None
    prior_experience: Optional[str] = None
    years_active: Optional[int] = None
    office_space_sqft: Optional[int] = None
    office_ownership: Optional[str] = None
    staff_count: Optional[int] = None
    internet_availability: bool = False
    computer_laptop: bool = False
    investment_capacity: Optional[str] = None
    source_of_funds: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    existing_loans: bool = False
    existing_loan_details: Optional[str] = None
    preferred_service_area: Optional[str] = None
    nearby_landmark: Optional[str] = None
    pincode: str
    aadhar_file_path: Optional[str] = None
    pan_file_path: Optional[str] = None
    photo_file_path: Optional[str] = None
    business_registration_file_path: Optional[str] = None
    bank_statement_file_path: Optional[str] = None
    doc_id_proof: bool = False
    doc_address_proof: bool = False
    doc_photographs: bool = False
    doc_business_registration: bool = False
    doc_bank_statement: bool = False
    agree_to_terms: bool = False
    submission_place: Optional[str] = None
    submission_date: Optional[date] = None
    admin_remarks: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class FranchiseApplicationUpdateStatus(BaseModel):
    status: FranchiseApplicationStatus
    admin_remarks: Optional[str] = Field(None, max_length=500)

class FranchiseApplicationListResponse(BaseModel):
    items: List[FranchiseApplicationResponse]
    total: int
    page: int
    limit: int
    pages: int

class FranchiseCreateFromApplication(BaseModel):
    application_id: str
    password: str = Field(..., min_length=8, description="Password for the new franchise user")

class FranchiseCreateResponse(BaseModel):
    success: bool
    message: str
    franchise_id: Optional[str] = None
    user_id: Optional[str] = None