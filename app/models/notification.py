from sqlalchemy import Column
from sqlalchemy import String,ForeignKey
from sqlalchemy import Boolean
from sqlalchemy import DateTime

from datetime import datetime
from datetime import timedelta

import uuid

from app.core.database import Base
import pytz

IST = pytz.timezone("Asia/Kolkata")
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))
    title = Column(String(255),nullable=False)
    message = Column(String(1000),nullable=False)
    type = Column(String(50),default="order")
    is_read = Column(Boolean,default=False)
    order_id = Column(String(36),ForeignKey("orders.id"),nullable=False)
    created_at = Column(DateTime(timezone=True),default=lambda: datetime.now(IST))
    expires_at = Column(DateTime(timezone=True),default=lambda: datetime.now(IST) + timedelta(hours=5))
    
    
    
    