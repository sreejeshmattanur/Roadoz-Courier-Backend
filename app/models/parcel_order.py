import uuid
from datetime import datetime
from typing import Optional

import pytz
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Numeric, Integer, Boolean, text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

IST = pytz.timezone("Asia/Kolkata")

def _indian_time():
    return datetime.now(IST)

# ── Parcel Sender ────────────────────────────────────────────────────────────

class ParcelSender(Base):
    __tablename__ = "parcel_senders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    alternate_mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line_1: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Ownership / scope
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    franchise_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("warehouse_addresses.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time, onupdate=_indian_time)

# ── Parcel Receiver ──────────────────────────────────────────────────────────

class ParcelReceiver(Base):
    __tablename__ = "parcel_receivers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    alternate_mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line_1: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Ownership / scope
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    franchise_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("warehouse_addresses.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time, onupdate=_indian_time)

# ── Parcel Order ────────────────────────────────────────────────────────────

class ParcelOrder(Base):
    __tablename__ = "parcel_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    barcode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sender_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parcel_senders.id", ondelete="SET NULL"), nullable=True, index=True)
    receiver_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("parcel_receivers.id", ondelete="SET NULL"), nullable=True, index=True)

    # Payment
    payment_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Prepaid | COD | To Pay | Credit
    cod_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    prepaid_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    to_pay_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    credit_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    rov: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # owner_risk | carrier_risk
    order_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))

    # Freight (all manual – user enters exactly what they want)
    service_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, server_default=text("'Surface'"))
    freight_charge: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))
    freight_gst: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))
    total_freight: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))
    extra_charge: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))

    # Package dimensions (single package – simple parcel)
    weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    length_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    breadth_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    total_boxes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default=text("1"))

    # Product
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default=text("1"))

    # Other
    gst_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    eway_bill_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    invoicenumber: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    insurance: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    regional_area: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, server_default=text("0"))
    remarks: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Processing'"))

    # Ownership / scope
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    franchise_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("warehouse_addresses.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_indian_time, onupdate=_indian_time)

    # Relationships
    creator = relationship("User", lazy="selectin")
    franchise = relationship("Franchise", lazy="selectin")
    sender = relationship("ParcelSender", lazy="selectin")
    receiver = relationship("ParcelReceiver", lazy="selectin")
