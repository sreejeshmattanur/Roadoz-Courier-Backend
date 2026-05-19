import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    calculator_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    shipment_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    payment_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    risk_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    min_weight: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_weight: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_per_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    cod_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    reverse_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    fuel_surcharge_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    insurance_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    gst_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("18"))
    volumetric_divisor: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("5000"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
