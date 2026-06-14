from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.schemas.remittance import (
    RemittanceSummaryOut,
    RemittanceOut,
    RemittanceListResponse,
    RemittanceCreateRequest,
    RemittanceMarkRemittedRequest,
)
from app.services.remittance_service import (
    get_remittance_summary,
    list_remittances,
    create_remittance,
    mark_remitted,
    get_remittance,
)

router = APIRouter(prefix="/remittances", tags=["Remittances"])


# ── Summary dashboard ─────────────────────────────────────────────────────


@router.get("/summary", response_model=RemittanceSummaryOut)
async def get_summary_endpoint(
    franchise_id: Optional[str] = Query(None, description="Admin: filter by franchise ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    return await get_remittance_summary(db, current_user, franchise_id=franchise_id)


# ── List remittances ──────────────────────────────────────────────────────


@router.get("", response_model=RemittanceListResponse)
async def list_remittances_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    franchise_id: Optional[str] = Query(None, description="Admin: filter by franchise ID"),
    status: Optional[str] = Query(None, description="Filter by status: pending, processing, remitted"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    return await list_remittances(
        db, current_user,
        page=page, limit=limit,
        franchise_id=franchise_id, status_filter=status,
    )


# ── Get single remittance ────────────────────────────────────────────────


@router.get("/{remittance_id}", response_model=RemittanceOut)
async def get_remittance_endpoint(
    remittance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    return await get_remittance(db, remittance_id, current_user)


# ── Create remittance batch (admin) ──────────────────────────────────────


@router.post("", response_model=RemittanceOut, status_code=201)
async def create_remittance_endpoint(
    data: RemittanceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:manage")),
):
    return await create_remittance(db, data)


# ── Mark as remitted (admin) ─────────────────────────────────────────────


@router.patch("/{remittance_id}/remit", response_model=RemittanceOut)
async def mark_remitted_endpoint(
    remittance_id: str,
    data: RemittanceMarkRemittedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:manage")),
):
    return await mark_remitted(
        db, remittance_id,
        reference_number=data.reference_number,
        remarks=data.remarks,
    )
