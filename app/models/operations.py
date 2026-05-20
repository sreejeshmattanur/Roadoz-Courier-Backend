import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    franchise_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    expense_head: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    franchise = relationship("Franchise", lazy="selectin")


class CashVoucher(Base):
    __tablename__ = "cash_vouchers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    voucher_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    franchise_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'Cash'"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    franchise = relationship("Franchise", lazy="selectin")


class StaffAttendance(Base):
    __tablename__ = "staff_attendance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    franchise_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'present'"))
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("User", lazy="selectin")
    franchise = relationship("Franchise", lazy="selectin")


class Manifest(Base):
    __tablename__ = "manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    manifest_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    franchise_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True)
    manifest_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    route: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'created'"))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    orders = relationship("ManifestOrder", back_populates="manifest", cascade="all, delete-orphan", lazy="selectin")
    franchise = relationship("Franchise", lazy="selectin")


class ManifestOrder(Base):
    __tablename__ = "manifest_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    manifest_id: Mapped[str] = mapped_column(String(36), ForeignKey("manifests.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    manifest = relationship("Manifest", back_populates="orders")
    order = relationship("Order", lazy="selectin")


class PodRecord(Base):
    __tablename__ = "pod_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    receiver_name: Mapped[str] = mapped_column(String(150), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivery_staff_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    otp_verified: Mapped[bool] = mapped_column(Integer, nullable=False, server_default=text("0"))
    signature_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    order = relationship("Order", lazy="selectin")
