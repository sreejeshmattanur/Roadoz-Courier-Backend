# app/schemas/auth_schema.py

from pydantic import BaseModel, EmailStr


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