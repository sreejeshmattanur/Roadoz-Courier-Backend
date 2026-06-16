from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.models.user import User
from app.models.consigeeauth import AuthUser
from app.models.franchise import Franchise
from app.models.user_franchise import FranchiseApplicationbyUser
from app.dependencies.role_checker import get_current_user, require_permission
from app.schemas.user_franchise import (
    FranchiseApplicationCreate,
    FranchiseApplicationResponse,
    FranchiseApplicationListResponse,
    FranchiseApplicationUpdateStatus,
    FranchiseCreateFromApplication,
    FranchiseCreateResponse
)
from sqlalchemy import select
from app.dependencies.consigeeuser import get_current_user as get_current_auth_user
from app.services.user_franchise import (
    create_franchise_application,
    upload_application_document,
    approve_franchise_application,
    reject_franchise_application,
    list_franchise_applications
)

router = APIRouter(prefix="/franchise-applications", tags=["Franchise Applications"])


@router.post("", response_model=FranchiseApplicationResponse, status_code=201)
async def create_application(
    data: FranchiseApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_auth_user: AuthUser = Depends(get_current_auth_user)  # Custom auth user dependency
):
    """Create a new franchise application (Auth User)"""
    return await create_franchise_application(db, data, current_auth_user.id)


@router.post("/{application_id}/upload/{document_type}")
async def upload_document(
    application_id: str,
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_auth_user: AuthUser = Depends(get_current_auth_user),
):
    """Upload document for franchise application (Admin only)"""
    return await upload_application_document(db, application_id, document_type, file, current_auth_user)


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