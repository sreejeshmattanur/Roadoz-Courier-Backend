from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    RoleCheckRequest,
    RoleCheckResponse,
    SendOTPRequest,
    VerifyOTPRequest,
    OTPResponse,
)
from app.services.auth_service import authenticate_user, get_user_role_by_email
from app.services.otp_service import send_otp, verify_otp
from app.utils.jwt import verify_refresh_token, create_access_token, create_refresh_token
from app.core.security import oauth2_scheme
from app.utils.redis import blacklist_token
from app.dependencies.role_checker import get_current_user
from app.models.user import User
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    """
    Unified login endpoint for Super Admin and Franchise users.

    - **Super Admin**: provide email + password only.
    - **Franchise**: provide email + password + franchise_code.
    """
    return await authenticate_user(db, request, http_request)


@router.post("/role", response_model=RoleCheckResponse)
async def get_role(request: RoleCheckRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    return await get_user_role_by_email(db, request.email, http_request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, http_request: Request):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = verify_refresh_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Store user_id in http_request.state for ActivityLoggingMiddleware
    http_request.state.user_id = payload["user_id"]
    token_data = {
        "user_id": payload["user_id"],
        "email": payload["email"],
        "role_id": payload.get("role_id"),
        "role": payload.get("role"),
        "permissions": list(payload.get("permissions") or []),
        "franchise_id": payload.get("franchise_id"),
        "franchise_code": payload.get("franchise_code"),
    }

    franchise_info = None
    if payload.get("franchise_id"):
        from app.schemas.auth import FranchiseInfo
        franchise_info = FranchiseInfo(
            id=payload["franchise_id"],
            franchise_code=payload.get("franchise_code", ""),
            name=payload.get("role", ""),
        )

    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=(
            {"id": payload.get("role_id"), "name": payload.get("role")}
            if payload.get("role")
            else None
        ),
        permissions=list(payload.get("permissions") or []),
        franchise=franchise_info,
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """Blacklist the current access token (logout)."""
    await blacklist_token(token, expire=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return {"message": "Logged out successfully"}


@router.post("/send-otp", response_model=OTPResponse)
async def send_otp_endpoint(request: SendOTPRequest):
    """
    Send a 6-digit OTP via email (SMTP) or SMS (Twilio).

    - Provide **email** for email OTP.
    - Provide **phone** for SMS OTP.
    - **purpose**: login | password_reset | franchise_auth
    """
    if not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either email or phone",
        )

    if request.email:
        await send_otp(request.email, request.purpose, via="email")
        return OTPResponse(
            message=f"OTP sent to {request.email}",
            expires_in=settings.OTP_EXPIRE_MINUTES * 60,
        )
    else:
        await send_otp(request.phone, request.purpose, via="sms")
        return OTPResponse(
            message=f"OTP sent to {request.phone}",
            expires_in=settings.OTP_EXPIRE_MINUTES * 60,
        )


@router.post("/verify-otp")
async def verify_otp_endpoint(request: VerifyOTPRequest):
    """
    Verify a previously sent OTP.

    - **identifier**: the email or phone the OTP was sent to.
    - **otp**: the 6-digit code.
    - **purpose**: must match the purpose used in send-otp.
    """
    await verify_otp(request.identifier, request.otp, request.purpose)
    return {"message": "OTP verified successfully", "verified": True}
