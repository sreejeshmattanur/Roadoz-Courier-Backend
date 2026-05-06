
from pydantic import BaseModel, Field,EmailStr
from typing import Optional
from datetime import datetime

class WarehouseCreate(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100)
    contact_name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=1, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    address_line_1: str = Field(..., min_length=1, max_length=500)
    address_line_2: Optional[str] = None
    pincode: str = Field(..., min_length=1, max_length=10)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    country: str = Field(default="India", max_length=100)


class WarehouseResponse(BaseModel):
    id: str
    nickname: str
    contact_name: str
    phone: str
    email: Optional[str]
    address_line_1: str
    address_line_2: Optional[str]
    pincode: str
    city: str
    state: str
    country: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    
    

class WarehouseAddressUpdate(BaseModel):
    nickname: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class WarehouseAddressResponse(BaseModel):
    id: str
    user_id: str
    franchise_id: Optional[str]
    nickname: str
    contact_name: str
    phone: str
    email: Optional[str]
    address_line_1: str
    address_line_2: Optional[str]
    pincode: str
    city: str
    state: str
    country: str

    class Config:
        from_attributes = True    