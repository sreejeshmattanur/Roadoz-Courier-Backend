from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.trip_sheet import TripSheet
from app.modules.fleet.constants import SHEET_STATUS_COMPLETED
from app.modules.fleet.dependencies.require_driver import require_driver
from app.modules.fleet.models.driver import Driver
from app.modules.fleet.schemas.trip_sheet_driver import (
    AvailabilityRequest,
    CashPaymentRequest,
    LocationPingRequest,
    SuccessDataResponse,
    TodayTripsResponse,
    TripRespondRequest,
    TripStatusUpdateRequest,
    VerifyDropRequest,
    VerifyPickupRequest,
)
from app.modules.fleet.services.driver_trip_execution_service import (
    complete_trip,
    get_payment_info,
    get_payment_status,
    get_trip_detail,
    submit_cash_payment,
    update_order_status,
    verify_drop,
    verify_pickup,
)
from app.modules.fleet.services.driver_scan_service import execute_scan_for_driver, lookup_barcode_for_driver
from app.modules.fleet.services.driver_dashboard_service import get_driver_dashboard
from app.modules.fleet.services.trip_sheet_driver_service import (
    export_order_history,
    list_active_trips,
    list_new_trips,
    list_order_history,
    respond_to_sheet,
)
from app.services.export_service import export_to_csv, export_to_excel, export_to_pdf

router = APIRouter(prefix="/api/v1/driver", tags=["Driver Runtime"])


@router.get("/dashboard", response_model=SuccessDataResponse)
async def driver_dashboard(
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    return SuccessDataResponse(success=True, data=await get_driver_dashboard(db, driver))


@router.patch("/availability", response_model=SuccessDataResponse)
async def set_availability(
    payload: AvailabilityRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    if payload.isOnline and driver.onboarding_status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver not approved")
    driver.online = payload.isOnline
    if payload.location:
        meta = dict(driver.meta or {})
        meta["last_location"] = payload.location
        driver.meta = meta
    await db.flush()
    return SuccessDataResponse(
        success=True,
        data={"isOnline": driver.online, "updatedAt": datetime.utcnow().isoformat()},
    )


@router.post("/location", status_code=204)
async def location_ping(
    payload: LocationPingRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    meta = dict(driver.meta or {})
    meta["last_location"] = {
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "tripSheetId": payload.tripSheetId,
        "timestamp": (payload.timestamp or datetime.utcnow()).isoformat(),
    }
    driver.meta = meta
    await db.flush()


@router.get("/trips/new", response_model=SuccessDataResponse)
async def get_new_trips(driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)):
    data = await list_new_trips(db, driver)
    return SuccessDataResponse(success=True, count=len(data), data=data)


@router.get("/trips/active", response_model=SuccessDataResponse)
async def get_active_trips(driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)):
    data = await list_active_trips(db, driver)
    return SuccessDataResponse(success=True, totalActive=len(data), data=data)


@router.get("/trips/today", response_model=TodayTripsResponse)
async def get_today_trips(driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)):
    return TodayTripsResponse(newTrips=await list_new_trips(db, driver), todayTrips=await list_active_trips(db, driver))


@router.post("/trip-sheets/{trip_sheet_id}/respond", response_model=SuccessDataResponse)
async def respond_trip_sheet(
    trip_sheet_id: str,
    payload: TripRespondRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    result = await respond_to_sheet(db, driver, trip_sheet_id, payload)
    return SuccessDataResponse(success=True, message="Trip updated.", data=result)


@router.get("/trips/{order_id}", response_model=SuccessDataResponse)
async def trip_detail(order_id: str, driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)):
    return SuccessDataResponse(success=True, data=await get_trip_detail(db, driver, order_id))


@router.patch("/trips/{order_id}/status", response_model=SuccessDataResponse)
async def trip_status(
    order_id: str,
    payload: TripStatusUpdateRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    data = await update_order_status(db, driver, order_id, payload)
    message = data.pop("message", None)
    return SuccessDataResponse(success=True, message=message, data=data)


@router.post("/trips/{order_id}/verify-pickup", response_model=SuccessDataResponse)
async def trip_verify_pickup(
    order_id: str,
    payload: VerifyPickupRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    data = await verify_pickup(db, driver, order_id, payload)
    message = data.pop("message", None)
    return SuccessDataResponse(success=True, message=message, data=data)


@router.post("/trips/{order_id}/verify-drop", response_model=SuccessDataResponse)
async def trip_verify_drop(
    order_id: str,
    payload: VerifyDropRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    data = await verify_drop(db, driver, order_id, payload)
    message = data.pop("message", None)
    return SuccessDataResponse(success=True, message=message, data=data)


@router.post("/trips/{order_id}/complete")
async def trip_complete(
    order_id: str, driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)
):
    return await complete_trip(db, driver, order_id)


@router.get("/payment/{order_id}", response_model=SuccessDataResponse)
async def payment_info(
    order_id: str, driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)
):
    return SuccessDataResponse(success=True, data=await get_payment_info(db, driver, order_id))


@router.get("/payment/status/{payment_reference}", response_model=SuccessDataResponse)
async def payment_status(payment_reference: str, db: AsyncSession = Depends(get_db)):
    return SuccessDataResponse(success=True, data=await get_payment_status(db, payment_reference))


@router.post("/payment/cash")
async def payment_cash(
    payload: CashPaymentRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    return await submit_cash_payment(db, driver, payload)


@router.get("/profile", response_model=SuccessDataResponse)
async def driver_profile(driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)):
    completed = (
        await db.execute(
            select(func.count())
            .select_from(TripSheet)
            .where(TripSheet.driver_id == driver.id, TripSheet.driver_status == SHEET_STATUS_COMPLETED)
        )
    ).scalar_one()
    vehicle = None
    if driver.vehicle:
        v = driver.vehicle
        vehicle = {
            "type": v.type,
            "registrationNumber": v.plate_number,
            "make": v.make,
            "model": v.model,
            "year": v.year,
            "color": v.color,
        }
    await db.refresh(driver, ["user"])
    return SuccessDataResponse(
        success=True,
        data={
            "id": driver.id,
            "firstName": driver.first_name,
            "lastName": driver.last_name,
            "email": driver.user.email if driver.user else "",
            "phone": driver.phone,
            "avatarUrl": None,
            "isVerified": driver.onboarding_status == "approved",
            "onboardingStatus": driver.onboarding_status,
            "isOnline": driver.online,
            "rating": 0,
            "totalTrips": completed,
            "vehicle": vehicle,
        },
    )


@router.get("/orders/history")
async def orders_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    return await list_order_history(db, driver, page, limit)


@router.get("/orders/export")
async def orders_export(
    format: str = Query(..., description="pdf, csv, or excel"),
    range: str | None = Query(None, description="this_week, this_month, last_month, or all"),
    startDate: date | None = Query(None),
    endDate: date | None = Query(None),
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    fmt = format.lower().strip()
    if fmt not in {"pdf", "csv", "excel"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="format must be one of: pdf, csv, excel",
        )
    report_data = await export_order_history(db, driver, range, startDate, endDate)
    items = report_data.get("items") or []
    if not items:
        return {"success": True, "data": {"rows": 0}}

    if fmt == "csv":
        return Response(
            content=export_to_csv(report_data),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="trip_report.csv"'},
        )
    if fmt == "excel":
        return Response(
            content=export_to_excel(report_data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="trip_report.xlsx"'},
        )
    return Response(
        content=export_to_pdf(report_data),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="trip_report.pdf"'},
    )


@router.get("/scan/{barcode}", response_model=SuccessDataResponse)
async def scan_lookup(
    barcode: str, driver: Driver = Depends(require_driver), db: AsyncSession = Depends(get_db)
):
    return SuccessDataResponse(success=True, data=await lookup_barcode_for_driver(db, driver, barcode))


@router.post("/scan/{barcode}/execute", response_model=SuccessDataResponse)
async def scan_execute(
    barcode: str,
    payload: LocationPingRequest,
    driver: Driver = Depends(require_driver),
    db: AsyncSession = Depends(get_db),
):
    return SuccessDataResponse(
        success=True,
        data=await execute_scan_for_driver(db, driver, barcode, payload.latitude, payload.longitude),
    )
