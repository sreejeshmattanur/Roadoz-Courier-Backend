# app/routes/auth_email.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

from app.models.consigeeauth import AuthUser

from app.schemas.consigeeauth import (
    RegisterRequest,
    SendOTPRequest,
    VerifyOTPRequest,
    PhoneRegisterRequest,
    SendOTPRequestByphone,
    VerifyOTPRequestByphone
    
)
from datetime import datetime, timedelta    
import random


from app.services.email_service import send_otp_email

from app.utils.jwt_token import create_access_token,create_refresh_token

router = APIRouter(prefix="/email-auth",tags=["User Email Authentication"])

    
    
@router.post("/register")
async def register_user(payload: RegisterRequest,db: AsyncSession = Depends(get_db)):
    
    result = await db.execute(select(AuthUser).where(AuthUser.email == payload.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered")
    user = AuthUser(
        name=payload.name,
        email=payload.email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "message": "User registered successfully",
        "user_id": user.id
    }    
    




@router.post("/send-otp")
async def send_otp(
    payload: SendOTPRequest,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.email == payload.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    otp = str(random.randint(1000, 9999))
    user.otp = otp
    await db.commit()
    email_sent = send_otp_email(payload.email, otp)
    if not email_sent:
        raise HTTPException(status_code=500,detail="Unable to send OTP email")
    return {"message": "OTP sent successfully"}
    
    

@router.post("/verify-otp")
async def verify_otp(payload: VerifyOTPRequest,db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuthUser).where(AuthUser.email == payload.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    if user.otp != payload.otp:
        raise HTTPException(status_code=400,detail="Invalid OTP")
    user.is_verified = True
    user.otp = None
    await db.commit()
    token = create_access_token({
        "user_id": user.id,
        "email": user.email
    })
    refresh_token = create_refresh_token({
    "user_id": user.id,
    "phone": user.email
    })
    return {
        "message": "Login successful",
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email
        }
    }
    
    

@router.post("/register-phone")
async def register_phone(payload: PhoneRegisterRequest,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.phone == payload.phone))
    user = result.scalar_one_or_none()
    if user:
        return {"message": "Phone already registered"}
    user = AuthUser(
        phone=payload.phone,
        name=payload.name if payload.email else None,
        email=payload.email if payload.email else None)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "message": "Phone registered successfully","user_id": user.id}



@router.post("/send-otpbyphone")
async def send_otp(payload: SendOTPRequestByphone,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.phone == payload.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    otp = str(random.randint(100000, 999999))
    user.otp = otp
    user.is_verified = False
    user.updated_at = datetime.utcnow()
    await db.commit()
    print(f"OTP sent to {payload.phone}: {otp}")
    return {"message": "OTP sent successfully"}


@router.post("/verify-otpbyphone")
async def verify_otp(payload: VerifyOTPRequestByphone,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.phone == payload.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.otp != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    user.is_verified = True
    user.otp = None   
    await db.commit()
    await db.refresh(user)
    token = create_access_token({
        "user_id": user.id,
        "phone": user.phone
    })
    refresh_token = create_refresh_token({
        "user_id": user.id,
        "phone": user.phone
    })
    return {
        "message": "Login successful",
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "phone": user.phone
        }
    }    