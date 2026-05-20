from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.services.print_service import (
    awb_print_html,
    daily_booking_print_html,
    delivery_run_sheet_html,
    invoice_print_html,
    shipping_label_html,
)

router = APIRouter(prefix="/prints", tags=["Print Formats"])


@router.get("/orders/{order_id}/awb", response_class=HTMLResponse)
async def print_awb_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return HTMLResponse(await awb_print_html(db, current_user, order_id))


@router.get("/orders/{order_id}/label", response_class=HTMLResponse)
async def print_shipping_label_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return HTMLResponse(await shipping_label_html(db, current_user, order_id))


@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
async def print_invoice_endpoint(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    return HTMLResponse(await invoice_print_html(db, current_user, invoice_id))


@router.get("/reports/daily-booking", response_class=HTMLResponse)
async def print_daily_booking_endpoint(
    report_date: date | None = Query(None),
    franchise_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return HTMLResponse(await daily_booking_print_html(db, current_user, report_date, franchise_id))


@router.get("/reports/delivery-run-sheet", response_class=HTMLResponse)
async def print_delivery_run_sheet_endpoint(
    run_date: date | None = Query(None),
    franchise_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    return HTMLResponse(await delivery_run_sheet_html(db, current_user, run_date, franchise_id))
