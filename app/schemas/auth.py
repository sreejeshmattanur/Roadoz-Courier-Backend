from pydantic import BaseModel, EmailStr
from typing import Optional


class RoleOut(BaseModel):
    id: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    franchise_code: Optional[str] = None  # Required only for franchise login


class RoleCheckRequest(BaseModel):
    email: EmailStr


class RoleCheckResponse(BaseModel):
    role: Optional[RoleOut] = None
    requires_franchise_code: bool


class FranchiseInfo(BaseModel):
    id: str
    franchise_code: str
    name: str


class WarehouseInfo(BaseModel):
    id: str
    nickname: str
    contact_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: Optional[RoleOut] = None
    permissions: list[str] = []
    franchise: Optional[FranchiseInfo] = None
    warehouse: Optional[WarehouseInfo] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class SendOTPRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    purpose: str = "login"  # login | password_reset | franchise_auth


class VerifyOTPRequest(BaseModel):
    identifier: str  # email or phone
    otp: str
    purpose: str = "login"


class OTPResponse(BaseModel):
    message: str
    expires_in: int  # seconds
