import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Boolean, Text, Integer, Enum ,text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class FranchiseApplicationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"

class FranchiseApplicationbyUser(Base):
    __tablename__ = "franchise_applications_byuser"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Auth User reference (who applied)
    auth_user_id: Mapped[str] = mapped_column(
        String(36), 
        ForeignKey("auth_users.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Application Status
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        server_default=text("'pending'")
    )
    
    # Personal Information
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Business Information
    proposed_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ownership_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detailed_business_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prior_experience: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Infrastructure
    office_space_sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    office_ownership: Mapped[str | None] = mapped_column(String(20), nullable=True)
    staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internet_availability: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    computer_laptop: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    
    # Financial
    investment_capacity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_of_funds: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    existing_loans: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    existing_loan_details: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    
    # Area
    preferred_service_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nearby_landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pincode: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    
    # Documents (file paths)
    aadhar_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pan_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_registration_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bank_statement_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Document checkboxes
    doc_id_proof: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_address_proof: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_photographs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_business_registration: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_bank_statement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    
    # Terms
    agree_to_terms: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    submission_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Admin remarks
    admin_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Meta
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
    
    # Relationships
    auth_user = relationship("AuthUser", foreign_keys=[auth_user_id])
    approver = relationship("User", foreign_keys=[approved_by])
    
    @property
    def is_approved(self) -> bool:
        return self.status == "approved"