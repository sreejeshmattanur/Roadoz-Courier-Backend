
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Enum,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from app.core.database import Base


class AuthUser(Base):

    __tablename__ = "auth_users"

    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=True)
    email = Column(String(255),unique=True,nullable=True,default=None)
    otp = Column(String(10), nullable=True)
    is_verified = Column(Boolean,default=False)
    created_at = Column(DateTime,default=datetime.utcnow)
    updated_at = Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    phone = Column(String(15),unique=True,nullable=True,default=None)
    auth_user_profiles = relationship("AuthUserProfile",back_populates="user",uselist=False,cascade="all, delete-orphan")
    
 
 
 
class AuthUserProfile(Base):
    __tablename__ = "auth_user_profiles"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False, unique=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    alternate_phone = Column(String(15), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    gender = Column(String(20), nullable=True)
    address_line_1 = Column(String(255), nullable=True)
    address_line_2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    country = Column(String(100), nullable=True, default="India")
    profile_image_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("AuthUser", back_populates="auth_user_profiles")