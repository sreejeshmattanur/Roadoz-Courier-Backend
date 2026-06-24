from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File,Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.models.user import User
from datetime import date, datetime
import re
import os
import shutil
from app.models.consigeeauth import AuthUser
from app.models.franchise import Franchise
from app.models.user_franchise import FranchiseApplicationbyUser
from app.dependencies.role_checker import get_current_user, require_permission
from app.schemas.user_franchise import (
    FranchiseApplicationResponse,
    FranchiseApplicationListResponse,
    FranchiseApplicationUpdateStatus,
    FranchiseCreateFromApplication,
    FranchiseCreateResponse
)
from sqlalchemy import select
from app.dependencies.consigeeuser import get_current_user as get_current_auth_user
from app.services.user_franchise import (
    approve_franchise_application,
    reject_franchise_application,
    list_franchise_applications
)
import uuid

router = APIRouter(prefix="/franchise-applications", tags=["Franchise Applications"])


UPLOAD_DIR = "uploads/franchise_documents"
ALLOWED_DOCUMENT_TYPES = {
    "aadhar": {"field": "aadhar_file_path", "doc_check": "doc_id_proof"},
    "pan": {"field": "pan_file_path", "doc_check": "doc_id_proof"},
    "photo": {"field": "photo_file_path", "doc_check": "doc_photographs"},
    "business_registration": {"field": "business_registration_file_path", "doc_check": "doc_business_registration"},
    "bank_statement": {"field": "bank_statement_file_path", "doc_check": "doc_bank_statement"},
}
ALLOWED_FILE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

@router.post("/create", status_code=201)
async def create_franchise_application(
    # Required Fields
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    pincode: str = Form(...),
    
    # Optional Fields
    date_of_birth: Optional[date] = Form(None),
    gender: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    permanent_address: Optional[str] = Form(None),
    proposed_location: Optional[str] = Form(None),
    ownership_type: Optional[str] = Form(None),
    detailed_business_address: Optional[str] = Form(None),
    prior_experience: Optional[str] = Form(None),
    years_active: Optional[int] = Form(None),
    office_space_sqft: Optional[int] = Form(None),
    office_ownership: Optional[str] = Form(None),
    staff_count: Optional[int] = Form(None),
    internet_availability: bool = Form(False),
    computer_laptop: bool = Form(False),
    investment_capacity: Optional[str] = Form(None),
    source_of_funds: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    account_number: Optional[str] = Form(None),
    existing_loans: bool = Form(False),
    existing_loan_details: Optional[str] = Form(None),
    preferred_service_area: Optional[str] = Form(None),
    nearby_landmark: Optional[str] = Form(None),
    doc_id_proof: bool = Form(False),
    doc_address_proof: bool = Form(False),
    doc_photographs: bool = Form(False),
    doc_business_registration: bool = Form(False),
    doc_bank_statement: bool = Form(False),
    agree_to_terms: bool = Form(True),
    submission_place: Optional[str] = Form(None),
    submission_date: Optional[date] = Form(None),
    
    # Document Files (Optional)
    aadhar_file: Optional[UploadFile] = File(None),
    pan_file: Optional[UploadFile] = File(None),
    photo_file: Optional[UploadFile] = File(None),
    business_registration_file: Optional[UploadFile] = File(None),
    bank_statement_file: Optional[UploadFile] = File(None),
    current_auth_user: AuthUser = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new franchise application with document uploads
    NO AUTHENTICATION REQUIRED
    """
    
    # ========== VALIDATION ==========
    
    # Validate required fields
    if not full_name or not email or not phone or not pincode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: full_name, email, phone, pincode"
        )
    
    # Validate phone number (10 digits)
    if not re.match(r'^[0-9]{10}$', phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Must be exactly 10 digits"
        )
    
    # Validate pincode (6 digits)
    if not re.match(r'^[0-9]{6}$', pincode):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pincode. Must be exactly 6 digits"
        )
    
    # Validate email
    if "@" not in email or "." not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )
    
    # Validate gender if provided
    if gender and gender.lower() not in ["male", "female", "other"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid gender. Must be: male, female, or other"
        )
    
    # Validate ownership_type if provided
    if ownership_type and ownership_type.lower() not in ["owned", "rented", "lease"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ownership_type. Must be: owned, rented, or lease"
        )
    
    # Check if agree_to_terms is True
    if not agree_to_terms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the terms and conditions"
        )
    
    # ========== CHECK FOR DUPLICATES ==========
    
    # Check if application exists with same email
    existing_email = await db.execute(
        select(FranchiseApplicationbyUser).where(
            FranchiseApplicationbyUser.email == email
        )
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An application with this email already exists"
        )
    
    # Check if application exists with same pincode
    existing_pincode = await db.execute(
        select(FranchiseApplicationbyUser).where(
            FranchiseApplicationbyUser.pincode == pincode
        )
    )
    if existing_pincode.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An application already exists for pincode {pincode}"
        )
    
    # ========== CREATE APPLICATION ==========
    
    application_id = str(uuid.uuid4())
    
    application = FranchiseApplicationbyUser(
        id=application_id,
        user_id=current_auth_user.id,
        status="pending",
        full_name=full_name,
        email=email,
        phone=phone,
        date_of_birth=date_of_birth,
        gender=gender.lower() if gender else None,
        current_address=current_address,
        permanent_address=permanent_address,
        proposed_location=proposed_location,
        ownership_type=ownership_type.lower() if ownership_type else None,
        detailed_business_address=detailed_business_address,
        prior_experience=prior_experience,
        years_active=years_active,
        office_space_sqft=office_space_sqft,
        office_ownership=office_ownership.lower() if office_ownership else None,
        staff_count=staff_count,
        internet_availability=internet_availability,
        computer_laptop=computer_laptop,
        investment_capacity=investment_capacity,
        source_of_funds=source_of_funds,
        bank_name=bank_name,
        account_number=account_number,
        existing_loans=existing_loans,
        existing_loan_details=existing_loan_details,
        preferred_service_area=preferred_service_area,
        nearby_landmark=nearby_landmark,
        pincode=pincode,
        doc_id_proof=doc_id_proof,
        doc_address_proof=doc_address_proof,
        doc_photographs=doc_photographs,
        doc_business_registration=doc_business_registration,
        doc_bank_statement=doc_bank_statement,
        agree_to_terms=agree_to_terms,
        submission_place=submission_place,
        submission_date=submission_date or date.today(),
    )
    
    db.add(application)
    await db.commit()
    await db.refresh(application)
    
    # ========== UPLOAD DOCUMENTS ==========
    
    uploaded_files = {}
    
    # Create upload directory if not exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Map form field names to document types and file objects
    file_mappings = {
        "aadhar": aadhar_file,
        "pan": pan_file,
        "photo": photo_file,
        "business_registration": business_registration_file,
        "bank_statement": bank_statement_file,
    }
    
    for doc_type, file_obj in file_mappings.items():
        if file_obj and file_obj.filename:
            try:
                # Validate file extension
                file_extension = os.path.splitext(file_obj.filename)[1].lower()
                if file_extension not in ALLOWED_FILE_EXTENSIONS:
                    uploaded_files[doc_type] = {
                        "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
                    }
                    continue
                
                # Generate filename
                filename = f"{application_id}_{doc_type}{file_extension}"
                file_path = os.path.join(UPLOAD_DIR, filename)
                
                # Save file
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file_obj.file, buffer)
                
                # Update application with file path
                field_map = ALLOWED_DOCUMENT_TYPES[doc_type]
                setattr(application, field_map["field"], file_path)
                
                # Mark document as submitted
                setattr(application, field_map["doc_check"], True)
                
                uploaded_files[doc_type] = {
                    "success": True,
                    "file_path": file_path
                }
                
            except Exception as e:
                uploaded_files[doc_type] = {
                    "error": str(e)
                }
    
    # Commit document updates
    await db.commit()
    await db.refresh(application)
    
    # ========== RETURN RESPONSE ==========
    
    return {
        "success": True,
        "message": "Franchise application created successfully",
        "application": {
            "id": application.id,
            "status": application.status,
            "full_name": application.full_name,
            "email": application.email,
            "phone": application.phone,
            "pincode": application.pincode,
            "created_at": application.created_at,
        },
        "uploaded_documents": uploaded_files
    }



@router.post("/approve", response_model=FranchiseCreateResponse)
async def approve_application(
    data: FranchiseCreateFromApplication,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("franchises:create")),
):
    """Approve franchise application and create franchise (Admin only)"""
    return await approve_franchise_application(db, data, current_user)


@router.post("/{application_id}/reject")
async def reject_application(
    application_id: str,
    data: FranchiseApplicationUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("franchises:create")),
):
    """Reject franchise application (Admin only)"""
    return await reject_franchise_application(db, application_id, data, current_user)


@router.get("", response_model=FranchiseApplicationListResponse)
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, on_hold"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("franchises:view")),
):
    """List all franchise applications (Admin only)"""
    return await list_franchise_applications(db, status, page, limit)


@router.get("/my-application", response_model=FranchiseApplicationResponse)
async def get_my_application(
    db: AsyncSession = Depends(get_db),
    current_auth_user: AuthUser = Depends(get_current_auth_user),
):
    """Get current auth user's franchise application"""
    app = await db.execute(
        select(FranchiseApplicationbyUser)
        .where(FranchiseApplicationbyUser.auth_user_id == current_auth_user.id)
        .order_by(FranchiseApplicationbyUser.created_at.desc())
    )
    app = app.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="No application found")
    return FranchiseApplicationResponse.model_validate(app)