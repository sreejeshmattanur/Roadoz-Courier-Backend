import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class RateMaster(Base):
    __tablename__ = "rate_master"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    service_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # "Surface", "Express"
    zone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    weight_up_to: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False) # e.g., 0.5 for 500gm, 1.0 for 1KG
    base_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))
