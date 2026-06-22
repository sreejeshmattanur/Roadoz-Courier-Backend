import os
import shutil
import uuid
from math import ceil
from datetime import datetime,date
from typing import Optional, List
from fastapi import HTTPException, status, UploadFile, File
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_password_hash
from app.models.user_franchise import FranchiseApplicationbyUser
from app.schemas.user_franchise import FranchiseApplicationResponse,FranchiseApplicationListResponse,FranchiseApplicationStatus,FranchiseApplicationUpdateStatus,FranchiseCreateFromApplication,FranchiseCreateResponse
from app.models.consigeeauth import AuthUser
from app.models.franchise import Franchise
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.franchise_service import _generate_franchise_code
from app.core.config import settings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib


# async def send_email(to_email: str, subject: str, body: str):
#     message = MIMEMultipart()
#     message["From"] = f"Roadoz-Courier <{settings.SMTP_USERNAME}>"
#     message["To"] = to_email
#     message["Subject"] = subject
#     message.attach(MIMEText(body, "plain"))
#     try:
#         await aiosmtplib.send(
#             message,
#             hostname=settings.SMTP_HOST,
#             port=settings.SMTP_PORT,
#             username=settings.SMTP_USERNAME,
#             password=settings.SMTP_PASSWORD,
#             start_tls=True
#         )
#         print("Email sent successfully")
#     except Exception as e:
#         print("Email error:", e)
#         raise e
    





async def send_email(to_email: str, subject: str, body: str):
    message = MIMEMultipart()
    message["From"] = f"Roadoz Courier <{settings.SMTP_USERNAME}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        print("EMAIL SENT SUCCESSFULLY")
        return True
    except Exception as e:
        print("SMTP ERROR:", e)
        return False
    
    
        
    
    
    
# UPLOAD_DIR = "uploads/franchise_documents"

# async def create_franchise_application(
#     db: AsyncSession, 
#     data: FranchiseApplicationCreate, 
# ) -> FranchiseApplicationResponse:
#     """Create a new franchise application from AuthUser"""
    
#     # Check if franchise already exists for this email or pincode
#     existing_franchise = await db.execute(
#         select(Franchise).where(
#             or_(
#                 Franchise.email == data.email,
#                 Franchise.pincode == data.pincode
#             )
#         )
#     )
#     if existing_franchise.scalar_one_or_none():
#         # Check if it's the same pincode
#         pincode_match = await db.execute(
#             select(Franchise).where(Franchise.pincode == data.pincode)
#         )
#         if pincode_match.scalar_one_or_none():
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"A franchise already exists for pincode {data.pincode}"
#             )
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Email already registered with a franchise"
#         )
    
#     # Create application
#     application = FranchiseApplicationbyUser(
#         id=str(uuid.uuid4()),
#         status="pending",
#         full_name=data.full_name,
#         email=data.email,
#         phone=data.phone,
#         date_of_birth=data.date_of_birth,
#         gender=data.gender,
#         current_address=data.current_address,
#         permanent_address=data.permanent_address,
#         proposed_location=data.proposed_location,
#         ownership_type=data.ownership_type,
#         detailed_business_address=data.detailed_business_address,
#         prior_experience=data.prior_experience,
#         years_active=data.years_active,
#         office_space_sqft=data.office_space_sqft,
#         office_ownership=data.office_ownership,
#         staff_count=data.staff_count,
#         internet_availability=data.internet_availability,
#         computer_laptop=data.computer_laptop,
#         investment_capacity=data.investment_capacity,
#         source_of_funds=data.source_of_funds,
#         bank_name=data.bank_name,
#         account_number=data.account_number,
#         existing_loans=data.existing_loans,
#         existing_loan_details=data.existing_loan_details,
#         preferred_service_area=data.preferred_service_area,
#         nearby_landmark=data.nearby_landmark,
#         pincode=data.pincode,
#         doc_id_proof=data.doc_id_proof,
#         doc_address_proof=data.doc_address_proof,
#         doc_photographs=data.doc_photographs,
#         doc_business_registration=data.doc_business_registration,
#         doc_bank_statement=data.doc_bank_statement,
#         agree_to_terms=data.agree_to_terms,
#         submission_place=data.submission_place,
#         submission_date=data.submission_date or date.today(),
#     )
    
#     db.add(application)
#     await db.commit()
#     await db.refresh(application)
    
#     return FranchiseApplicationResponse.model_validate(application)


# async def upload_application_document(
#     db: AsyncSession,
#     application_id: str,
#     document_type: str,
#     file: UploadFile,
# ) -> dict:
#     """Upload document for franchise application"""
    
#     # Check if application exists
#     app = await db.execute(
#         select(FranchiseApplicationbyUser).where(FranchiseApplicationbyUser.id == application_id)
#     )
#     app = app.scalar_one_or_none()
#     if not app:
#         raise HTTPException(status_code=404, detail="Application not found")
    
#     # Check if application is pending
#     if app.status != "pending":
#         raise HTTPException(
#             status_code=400,
#             detail=f"Cannot upload documents for {app.status} application"
#         )
    
#     # Create upload directory if not exists
#     os.makedirs(UPLOAD_DIR, exist_ok=True)
    
#     # Generate filename
#     file_extension = file.filename.split(".")[-1] if file.filename else "pdf"
#     filename = f"{application_id}_{document_type}.{file_extension}"
#     file_path = os.path.join(UPLOAD_DIR, filename)
    
#     # Save file
#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)
    
#     # Update application with file path
#     field_map = {
#         "aadhar": "aadhar_file_path",
#         "pan": "pan_file_path",
#         "photo": "photo_file_path",
#         "business_registration": "business_registration_file_path",
#         "bank_statement": "bank_statement_file_path",
#     }
    
#     if document_type not in field_map:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid document type. Allowed: {list(field_map.keys())}"
#         )
    
#     setattr(app, field_map[document_type], file_path)
    
#     # Mark document as submitted
#     doc_check_map = {
#         "aadhar": "doc_id_proof",
#         "pan": "doc_id_proof",
#         "photo": "doc_photographs",
#         "business_registration": "doc_business_registration",
#         "bank_statement": "doc_bank_statement",
#     }
#     if document_type in doc_check_map:
#         setattr(app, doc_check_map[document_type], True)
    
#     await db.commit()
#     await db.refresh(app)
    
#     return {
#         "success": True,
#         "message": f"{document_type} uploaded successfully",
#         "file_path": file_path
#     }


async def approve_franchise_application(
    db: AsyncSession,
    data: FranchiseCreateFromApplication,
    admin_user: User
) -> FranchiseCreateResponse:
    """Approve franchise application and create actual franchise"""
    
    # Get application
    app = await db.execute(
        select(FranchiseApplicationbyUser).where(FranchiseApplicationbyUser.id == data.application_id)
    )
    app = app.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if app.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve {app.status} application"
        )
    
    # Check if franchise already exists for this pincode
    existing_franchise = await db.execute(
        select(Franchise).where(Franchise.pincode == app.pincode)
    )
    if existing_franchise.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"A franchise already exists for pincode {app.pincode}"
        )
    
    # Check if email already registered
    existing_user = await db.execute(
        select(User).where(User.email == app.email)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    try:
        # Generate franchise code
        franchise_code = await _generate_franchise_code(db, app.proposed_location)
        
        # Create User
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            name=app.full_name,
            email=app.email,
            password_hash=get_password_hash(data.password),
            phone=app.phone,
            address=app.current_address,
        )
        db.add(user)
        await db.flush()
        
        role_result = await db.execute(select(Role).where(Role.name == "franchise"))
        franchise_role = role_result.scalar_one_or_none()
        if not franchise_role:
            franchise_role = Role(id=str(uuid.uuid4()), name="franchise")
            db.add(franchise_role)
            await db.flush()
        
        # Assign role to user
        user_role_result = await db.execute(
            select(UserRole).where(UserRole.user_id == user.id)
        )
        mapping = user_role_result.scalar_one_or_none()
        if not mapping:
            db.add(UserRole(user_id=user.id, role_id=franchise_role.id))
        else:
            mapping.role_id = franchise_role.id
        
        # Create Franchise from application data
        franchise = Franchise(
            id=str(uuid.uuid4()),
            user_id=user.id,
            franchise_code=franchise_code,
            name=app.full_name,
            email=app.email,
            phone=app.phone,
            address=app.current_address,
            date_of_birth=app.date_of_birth,
            gender=app.gender,
            current_address=app.current_address,
            permanent_address=app.permanent_address,
            proposed_location=app.proposed_location,
            ownership_type=app.ownership_type,
            detailed_business_address=app.detailed_business_address,
            prior_experience=app.prior_experience,
            years_active=app.years_active,
            office_space_sqft=app.office_space_sqft,
            office_ownership=app.office_ownership,
            staff_count=app.staff_count,
            internet_availability=app.internet_availability,
            computer_laptop=app.computer_laptop,
            investment_capacity=app.investment_capacity,
            source_of_funds=app.source_of_funds,
            bank_name=app.bank_name,
            account_number=app.account_number,
            existing_loans=app.existing_loans,
            existing_loan_details=app.existing_loan_details,
            preferred_service_area=app.preferred_service_area,
            nearby_landmark=app.nearby_landmark,
            pincode=app.pincode,
            doc_id_proof=app.doc_id_proof,
            doc_address_proof=app.doc_address_proof,
            doc_photographs=app.doc_photographs,
            doc_business_registration=app.doc_business_registration,
            doc_bank_statement=app.doc_bank_statement,
            agree_to_terms=app.agree_to_terms,
            submission_place=app.submission_place,
            submission_date=app.submission_date,
            is_active=True,
        )
        db.add(franchise)
        await db.flush()
        
        # Update application status
        app.status = "approved"
        app.approved_by = admin_user.id
        app.approved_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(franchise)
        
        email_body = f"""
Hello {app.full_name},

Your Roadoz Courier franchise application has been approved successfully.
Your account has been created.

Login Details:
  Email: {app.email}
  Password: {data.password}
  Franchise Code: {franchise.franchise_code}

Thank you,
Roadoz Courier Team
        """
        await send_email(
            to_email=app.email,
            subject="Roadoz Courier Franchise Approved - Login Details",
            body=email_body
        )
                
        
        return FranchiseCreateResponse(
            success=True,
            message="Franchise created successfully",
            franchise_id=franchise.id,
            user_id=user.id
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating franchise: {str(e)}"
        )


async def reject_franchise_application(
    db: AsyncSession,
    application_id: str,
    data: FranchiseApplicationUpdateStatus,
    admin_user: User
) -> dict:
    """Reject franchise application"""
    
    app = await db.execute(
        select(FranchiseApplicationbyUser).where(FranchiseApplicationbyUser.id == application_id)
    )
    app = app.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    if app.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Application is already {app.status}"
        )
    
    app.status = "rejected"
    app.admin_remarks = data.admin_remarks
    app.approved_by = admin_user.id
    app.approved_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(app)
    
    return {
        "success": True,
        "message": "Application rejected successfully"
    }


async def list_franchise_applications(
    db: AsyncSession,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 10
) -> FranchiseApplicationListResponse:
    """List all franchise applications with pagination"""
    
    query = select(FranchiseApplicationbyUser)
    count_query = select(func.count()).select_from(FranchiseApplicationbyUser)
    
    if status:
        query = query.where(FranchiseApplicationbyUser.status == status)
        count_query = count_query.where(FranchiseApplicationbyUser.status == status)
    
    query = query.order_by(FranchiseApplicationbyUser.created_at.desc())
    
    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    applications = result.scalars().all()
    
    return FranchiseApplicationListResponse(
        items=[FranchiseApplicationResponse.model_validate(a) for a in applications],
        total=total,
        page=page,
        limit=limit,
        pages=ceil(total / limit) if total > 0 else 0,
    )