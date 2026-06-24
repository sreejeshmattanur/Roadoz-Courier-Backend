# app/routes/auth_email.py

from fastapi import APIRouter, Depends, HTTPException,status
from sqlalchemy.orm import Session
import random
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

from app.models.consigeeauth import AuthUser,AuthUserProfile
from app.models.consignee import Consignee
from app.schemas.consigeeauth import (
    RegisterRequest,
    SendOTPRequest,
    VerifyOTPRequest,
    PhoneRegisterRequest,
    SendOTPRequestByphone,
    VerifyOTPRequestByphone,
    UserProfileResponse,
    UserProfileUpdate,
    UserProfileCreate
    )
from datetime import datetime, timedelta    
import random
from app.services.consigeeimage_service import LocalImageService    
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form    
from typing import Optional    
from app.services.email_service import send_otp_email

from app.utils.jwt_token import create_access_token,create_refresh_token
from app.dependencies.consigeeuser import get_current_user

router = APIRouter(prefix="/email-auth",tags=["User Email Authentication"])

    
    
@router.post("/register")
async def register_user(payload: RegisterRequest,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthUser).where(AuthUser.email == payload.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400,detail="Email already registered")
    user = AuthUser(name=payload.name,email=payload.email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User registered successfully","user_id": user.id}    
    




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
    



# ////////////////////////////////////////////////////////////////////////////////////
# ///////////////////////////////////////////////////////////////////////////////////    AuthUser profile
    


@router.post("/create_profile", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    alternate_phone: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    address_line_1: Optional[str] = Form(None),
    address_line_2: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    country: Optional[str] = Form("India"),
    bio: Optional[str] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
    ):
    
    result = await db.execute(select(AuthUserProfile).where(AuthUserProfile.user_id == current_user.id))
    existing_profile = result.scalar_one_or_none()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,detail="Profile already exists for this user. Use update endpoint instead.")
    profile_image_url = None
    if profile_image:
        profile_image_url = await LocalImageService.save_profile_image(profile_image, current_user.id)
    dob = None
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid date format. Use YYYY-MM-DD")
    profile = AuthUserProfile(
        user_id=current_user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        alternate_phone=alternate_phone,
        date_of_birth=dob,
        gender=gender,
        address_line_1=address_line_1,
        address_line_2=address_line_2,
        city=city,
        state=state,
        pincode=pincode,
        country=country,
        bio=bio,
        profile_image_url=profile_image_url
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile





@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):
    
    result = await db.execute(select(AuthUserProfile).where(AuthUserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Profile not found. Please create a profile first.")
    return profile







@router.put("/update", response_model=UserProfileResponse)
async def update_profile(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    alternate_phone: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    address_line_1: Optional[str] = Form(None),
    address_line_2: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(AuthUserProfile).where(AuthUserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Profile not found. Please create a profile first.")
    if profile_image:
        profile_image_url = await LocalImageService.update_profile_image(
            profile_image, 
            current_user.id, 
            profile.profile_image_url
        )
        profile.profile_image_url = profile_image_url
    if date_of_birth:
        try:
            profile.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid date format. Use YYYY-MM-DD")
    if first_name is not None:
        profile.first_name = first_name
    if last_name is not None:
        profile.last_name = last_name
    if phone is not None:
        profile.phone = phone
    if alternate_phone is not None:
        profile.alternate_phone = alternate_phone
    if gender is not None:
        profile.gender = gender
    if address_line_1 is not None:
        profile.address_line_1 = address_line_1
    if address_line_2 is not None:
        profile.address_line_2 = address_line_2
    if city is not None:
        profile.city = city
    if state is not None:
        profile.state = state
    if pincode is not None:
        profile.pincode = pincode
    if country is not None:
        profile.country = country
    if bio is not None:
        profile.bio = bio
    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return profile