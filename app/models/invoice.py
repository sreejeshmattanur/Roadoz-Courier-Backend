import uuid
from datetime import datetime, date

from sqlalchemy import String, DateTime, Date, ForeignKey, Numeric, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Invoice(Base):
    """
    Periodic billing invoice for shipping services consumed by a franchise.
    """
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    franchise_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("franchises.id", ondelete="CASCADE"), nullable=True, index=True
    )

    description: Mapped[str] = mapped_column(String(500), nullable=False)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("18"))
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    orders_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # draft | issued | paid
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'issued'"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    # Relationships
    franchise = relationship("Franchise", lazy="selectin")
    invoice_orders = relationship(
        "InvoiceOrder", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class InvoiceOrder(Base):
    """
    Junction table linking an invoice to individual orders and their shipping charges.
    """
    __tablename__ = "invoice_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )

    shipping_charge: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    # Relationships
    invoice = relationship("Invoice", back_populates="invoice_orders")
    order = relationship("Order", lazy="selectin")
