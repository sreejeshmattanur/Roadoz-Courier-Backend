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