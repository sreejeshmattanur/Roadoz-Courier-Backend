# app/schemas/auth_schema.py
from typing import Optional
from pydantic import BaseModel, EmailStr
from pydantic import BaseModel, Field, validator
from datetime import datetime
import re


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str
    
    

class PhoneRegisterRequest(BaseModel):
    name:str | None = None
    phone: str
    email: str | None = None

class SendOTPRequestByphone(BaseModel):
    phone: str


class VerifyOTPRequestByphone(BaseModel):

    phone: str
    otp: str    
    
    
    



class UserProfileBase(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    alternate_phone: Optional[str] = Field(None, max_length=15)
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = Field(None, pattern="^(Male|Female|Other)$")
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    country: Optional[str] = Field("India", max_length=100)
    bio: Optional[str] = None

    @validator('phone', 'alternate_phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^[0-9]{10,15}$', v):
            raise ValueError('Phone number must be 10-15 digits')
        return v

    @validator('pincode')
    def validate_pincode(cls, v):
        if v and not re.match(r'^[0-9]{6}$', v):
            raise ValueError('Pincode must be 6 digits')
        return v

class UserProfileCreate(UserProfileBase):
    pass

class UserProfileUpdate(UserProfileBase):
    pass

class UserProfileResponse(UserProfileBase):
    id: str
    user_id: str
    profile_image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True