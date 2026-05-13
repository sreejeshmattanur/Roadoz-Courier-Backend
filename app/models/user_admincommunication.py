from sqlalchemy import (Column,Integer,String,Text,DateTime)
from datetime import datetime
import pytz
from app.core.database import Base
IST = pytz.timezone("Asia/Kolkata")
def indian_time():
    return datetime.now(IST)
class AdminandUserMessage(Base):
    __tablename__ = "adminandusermessages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(String(255))
    sender_type = Column(String(50))
    receiver_type = Column(String(50))
    receiver_id = Column(String(255))
    message = Column(Text)
    created_at = Column(DateTime(timezone=True),nullable=False,default=indian_time)
    updated_at = Column(DateTime(timezone=True),nullable=False,default=indian_time,onupdate=indian_time)