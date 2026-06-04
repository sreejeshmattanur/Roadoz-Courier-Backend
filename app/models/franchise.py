import uuid
from typing import TYPE_CHECKING
from datetime import datetime, date
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Date, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Franchise(Base):
    __tablename__ = "franchises"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,   # 🔥 important
        unique=True       # keep only if 1 user = 1 franchise
    )

    franchise_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Personal Info
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Business Info
    proposed_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ownership_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detailed_business_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prior_experience: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_active: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Infrastructure
    office_space_sqft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    office_ownership: Mapped[str | None] = mapped_column(String(20), nullable=True)
    staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    internet_availability: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0")
    )

    computer_laptop: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0")
    )

    # Financial
    investment_capacity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_of_funds: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    existing_loans: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0")
    )

    existing_loan_details: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Area
    preferred_service_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nearby_landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # pin_codes_covered: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pincode: Mapped[str] = mapped_column(String(6), nullable=False)

    # Documents
    doc_id_proof: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_address_proof: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_photographs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_business_registration: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    doc_bank_statement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))

    # Submission
    agree_to_terms: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    submission_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Employee counter — tracks last employee sequence for this franchise
    employee_counter: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Meta
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("1")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    employees: Mapped[list["User"]] = relationship(
        "User", foreign_keys="User.franchise_id", back_populates="franchise", lazy="selectin"
    )
    roles = relationship("Role", back_populates="franchise", cascade="all, delete-orphan")

    # Helpers
    @property
    def full_name(self) -> str:
        return self.name

    @property
    def email_id(self) -> str:
        return self.email

    @property
    def mobile_number(self) -> str | None:
        return self.phone
    
    
 

class OrderFranchiseAddress(Base):

    __tablename__ = "order_franchise_addresses"

    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36),ForeignKey("orders.id", ondelete="CASCADE"),nullable=False)
    franchise_address_id: Mapped[str] = mapped_column(String(36),ForeignKey("franchises.id", ondelete="CASCADE"),nullable=False)
    order = relationship("Order",back_populates="franchise_addresses")
    franchise_address = relationship("Franchise")    