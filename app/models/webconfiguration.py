from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean
from app.core.database import Base

class WebConfiguration(Base):
    __tablename__ = "web_configurations"
    id: Mapped[int] = mapped_column(primary_key=True)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    
    allow_order_create: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_to_pay: Mapped[bool] = mapped_column(Boolean, default=True)
    
    app_timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    
    razorpay_key_id: Mapped[str] = mapped_column(String(255),nullable=True)
    razorpay_secret_key: Mapped[str] = mapped_column(String(255),nullable=True)
    
    
    
    
    




    