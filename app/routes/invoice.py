from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.schemas.invoice import (
    InvoiceOut,
    InvoiceListResponse,
    InvoiceGenerateRequest,
    InvoiceMarkPaidRequest,
)
from app.services.invoice_service import (
    generate_invoice,
    list_invoices,
    get_invoice,
    mark_paid,
    generate_invoice_for_order,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


# ── List invoices ─────────────────────────────────────────────────────────


@router.get("", response_model=InvoiceListResponse)
async def list_invoices_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    franchise_id: Optional[str] = Query(None, description="Admin: filter by franchise ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    return await list_invoices(
        db, current_user,
        page=page, limit=limit,
        franchise_id=franchise_id,
    )


# ── Get single invoice ───────────────────────────────────────────────────


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice_endpoint(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    return await get_invoice(db, invoice_id, current_user)


# ── Generate invoice (admin) ─────────────────────────────────────────────


@router.post("/generate", response_model=InvoiceOut, status_code=201)
async def generate_invoice_endpoint(
    data: InvoiceGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:generate")),
):
    return await generate_invoice(db, data)


@router.post("/generate/order/{order_id}", response_model=InvoiceOut, status_code=201)
async def generate_invoice_for_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:generate")),
):
    return await generate_invoice_for_order(db, order_id)


# ── Mark invoice as paid (admin) ─────────────────────────────────────────


@router.patch("/{invoice_id}/pay", response_model=InvoiceOut)
async def mark_paid_endpoint(
    invoice_id: str,
    data: InvoiceMarkPaidRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:generate")),
):
    return await mark_paid(db, invoice_id)
