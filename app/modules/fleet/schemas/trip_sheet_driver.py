from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class MoneyOut(BaseModel):
    amount: float
    currency: str = "INR"


class LocationDetailOut(BaseModel):
    name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contactPhone: Optional[str] = None


class SheetSummaryOut(BaseModel):
    totalPackages: int
    destinationCity: Optional[str] = None


class TripListItemOut(BaseModel):
    id: str
    tripSheetId: str
    deliveryId: str
    orderId: str
    customerName: str
    status: str
    tripType: str = "PICKUP_AND_DELIVERY"
    isExpress: bool = False
    assignedTime: Optional[datetime] = None
    pickupLocation: LocationDetailOut
    dropLocation: LocationDetailOut
    estimatedDistance: Optional[str] = None
    estimatedDuration: Optional[str] = None
    earnings: MoneyOut
    package: Optional[dict] = None
    payment: Optional[dict] = None
    progress: Optional[str] = None
    sheetSummary: Optional[SheetSummaryOut] = None
    isAccepted: bool = False


class SuccessDataResponse(BaseModel):
    success: bool = True
    data: dict | list | None = None
    message: Optional[str] = None
    count: Optional[int] = None
    totalActive: Optional[int] = None


class TodayTripsResponse(BaseModel):
    newTrips: list[TripListItemOut]
    todayTrips: list[TripListItemOut]


class TripRespondRequest(BaseModel):
    action: Literal["ACCEPT", "DECLINE"]
    reason: Optional[str] = None
    driverLocation: Optional[dict] = None


class AvailabilityRequest(BaseModel):
    isOnline: bool
    location: Optional[dict] = None


class LocationPingRequest(BaseModel):
    latitude: float
    longitude: float
    tripSheetId: Optional[str] = None
    timestamp: Optional[datetime] = None


class TripStatusUpdateRequest(BaseModel):
    status: str
    location: Optional[dict] = None
    timestamp: Optional[datetime] = None
    reason: Optional[str] = None
    phase: Optional[Literal["PICKUP", "DELIVERY"]] = None

class VerifyPickupRequest(BaseModel):
    packageBarcode: Optional[str] = None
    photoUrl: Optional[str] = None
    notes: Optional[str] = None
    confirmedAt: Optional[datetime] = None
    location: Optional[dict] = None


class VerifyDropRequest(BaseModel):
    otp: Optional[str] = None
    receiverName: Optional[str] = None
    signatureUrl: Optional[str] = None
    photoUrl: Optional[str] = None
    collectedCash: float = 0
    confirmedAt: Optional[datetime] = None
    location: Optional[dict] = None


class CashPaymentRequest(BaseModel):
    orderId: str
    amount: float
    collectedAt: Optional[datetime] = None


class DriverProfileOut(BaseModel):
    id: str
    firstName: str
    lastName: str
    email: str
    phone: Optional[str] = None
    avatarUrl: Optional[str] = None
    isVerified: bool
    onboardingStatus: str
    isOnline: bool
    rating: float = 0
    totalTrips: int = 0
    vehicle: Optional[dict] = None


class DriverAuthResponse(BaseModel):
    token: str
    refreshToken: str
    userId: str
    driverId: str


class DriverOtpLoginRequest(BaseModel):
    phone: str
    otp: str = Field(..., pattern=r"^[0-9]{6}$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    newPassword: str = Field(..., min_length=8)


class ResendOtpRequest(BaseModel):
    phone: str
    purpose: str = "login"
