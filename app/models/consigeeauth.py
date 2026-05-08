
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Enum,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from app.core.database import Base


class AuthUser(Base):

    __tablename__ = "auth_users"

    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    email = Column(String(255),unique=True,nullable=False)
    otp = Column(String(10), nullable=True)
    is_verified = Column(Boolean,default=False)
    created_at = Column(DateTime,default=datetime.utcnow)
    updated_at = Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)