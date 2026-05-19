import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Numeric, Boolean, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class RateZone(Base):
    __tablename__ = "rate_zones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # Comma-separated list of states or specific identifiers
    state_mapping: Mapped[str] = mapped_column(Text, nullable=False) 

class RateCard(Base):
    __tablename__ = "rate_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # e.g. B2B, B2C
    shipment_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # e.g. SURFACE, AIR
    zone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    min_weight: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_weight: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    additional_kg_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    
    cod_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    insurance_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    appointment_charge: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))

class FuelConfig(Base):
    __tablename__ = "fuel_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))

class GSTConfig(Base):
    __tablename__ = "gst_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

class PincodeServiceability(Base):
    __tablename__ = "pincode_serviceability"

    pincode: Mapped[str] = mapped_column(String(20), primary_key=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    serviceable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
