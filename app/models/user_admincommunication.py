# from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
# from sqlalchemy.sql import func
# from datetime import datetime
# from app.core.database import Base
# import pytz
# IST = pytz.timezone("Asia/Kolkata")

# def indian_time():
#     return datetime.now(IST)



# class Message(Base):

#     __tablename__ = "messages"
#     id = Column(Integer, primary_key=True)
#     sender_id = Column(Integer, ForeignKey("users.id"))
#     receiver_id = Column(Integer, ForeignKey("users.id"))
#     message = Column(Text)
#     created_at = Column(DateTime(timezone=True),nullable=False,default=indian_time)
#     updated_at = Column(DateTime(timezone=True),nullable=False,default=indian_time,onupdate=indian_time)    