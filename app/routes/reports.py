from datetime import date
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.services.report_service import (
    # Existing
    cod_pending_report,
    customer_wise_booking_report,
    daily_booking_report,
    delivery_efficiency_report,
    delivery_status_report,
    franchise_settlement_report,
    gst_sales_report,
    monthly_revenue_analysis,
    pending_delivery_report,
    service_type_report,
    top_customer_report,
    # New
    day_close_report,
    branch_activity_report,
    user_activity_report,
    returned_shipment_report,
    collection_summary_report,
    outstanding_collection_report,
    daily_collection_report,
    cod_settlement_report,
    cod_commission_report,
    cash_book_report,
    expense_report,
    profit_loss_report,
    hsn_summary_report,
    gst_collection_summary,
    franchise_outstanding_report,
    franchise_collection_report,
    franchise_profitability_report,
    area_wise_business_report,
    performance_dashboard_report,
)
from app.services.export_service import export_to_csv, export_to_excel, export_to_pdf

router = APIRouter(prefix="/reports", tags=["Reports"])


def format_report_response(report_data: dict, format: str):
    if format == "json":
        return report_data
    
    filename_title = report_data.get("report", "Report").lower().replace(" ", "_")
    if format == "csv":
        csv_bytes = export_to_csv(report_data)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename_title}.csv"'}
        )
    elif format == "excel":
        excel_bytes = export_to_excel(report_data)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_title}.xlsx"'}
        )
    elif format == "pdf":
        pdf_bytes = export_to_pdf(report_data)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_title}.pdf"'}
        )
    return report_data


# ─── BOOKINGS REPORTS ────────────────────────────────────────────────────────

@router.get("/bookings/daily")
async def daily_booking_report_endpoint(
    report_date: date | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await daily_booking_report(db, current_user, report_date, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/bookings/customer-wise")
async def customer_wise_booking_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await customer_wise_booking_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/bookings/service-type")
async def service_type_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await service_type_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── DELIVERY REPORTS ────────────────────────────────────────────────────────

@router.get("/delivery/status")
async def delivery_status_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await delivery_status_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/delivery/pending")
async def pending_delivery_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await pending_delivery_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/delivery/returned")
async def returned_shipment_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await returned_shipment_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── OPERATIONS REPORTS ──────────────────────────────────────────────────────

@router.get("/operations/day-close")
async def day_close_report_endpoint(
    report_date: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await day_close_report(db, current_user, report_date, franchise_id)
    return format_report_response(data, format)


@router.get("/operations/branch-activity")
async def branch_activity_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await branch_activity_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/operations/user-activity")
async def user_activity_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await user_activity_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── COLLECTIONS AND COD REPORTS ─────────────────────────────────────────────

@router.get("/collections/summary")
async def collection_summary_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await collection_summary_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/collections/outstanding")
async def outstanding_collection_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await outstanding_collection_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/collections/daily")
async def daily_collection_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await daily_collection_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/cod/pending")
async def cod_pending_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    data = await cod_pending_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/cod/settlement")
async def cod_settlement_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    data = await cod_settlement_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/cod/commission")
async def cod_commission_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("remittances:view")),
):
    data = await cod_commission_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── FINANCE AND ACCOUNTS REPORTS ───────────────────────────────────────────

@router.get("/finance/cash-book")
async def cash_book_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await cash_book_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/finance/expense")
async def expense_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await expense_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/finance/profit-loss")
async def profit_loss_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await profit_loss_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── GST REPORTS ─────────────────────────────────────────────────────────────

@router.get("/gst/sales")
async def gst_sales_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await gst_sales_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/gst/hsn-summary")
async def hsn_summary_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await hsn_summary_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/gst/collection-summary")
async def gst_collection_summary_endpoint(
    year: int | None = Query(None, ge=2000, le=2100),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await gst_collection_summary(db, current_user, year, franchise_id)
    return format_report_response(data, format)


# ─── FRANCHISE REPORTS ────────────────────────────────────────────────────────

@router.get("/franchise/settlement")
async def franchise_settlement_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await franchise_settlement_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/franchise/outstanding")
async def franchise_outstanding_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await franchise_outstanding_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/franchise/collection")
async def franchise_collection_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await franchise_collection_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/franchise/profitability")
async def franchise_profitability_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("invoices:view")),
):
    data = await franchise_profitability_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


# ─── MIS REPORTS ─────────────────────────────────────────────────────────────

@router.get("/mis/monthly-revenue")
async def monthly_revenue_analysis_endpoint(
    year: int | None = Query(None, ge=2000, le=2100),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await monthly_revenue_analysis(db, current_user, year, franchise_id)
    return format_report_response(data, format)


@router.get("/mis/top-customers")
async def top_customer_report_endpoint(
    limit: int = Query(10, ge=1, le=100),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await top_customer_report(db, current_user, limit, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/mis/delivery-efficiency")
async def delivery_efficiency_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await delivery_efficiency_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/mis/area-wise-business")
async def area_wise_business_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await area_wise_business_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)


@router.get("/mis/performance-dashboard")
async def performance_dashboard_report_endpoint(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    franchise_id: str | None = Query(None),
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("orders:view")),
):
    data = await performance_dashboard_report(db, current_user, date_from, date_to, franchise_id)
    return format_report_response(data, format)
