from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.schemas.wallet import (
    WalletOut,
    WalletTransactionOut,
    WalletTransactionListResponse,
    WalletRechargeRequest,
    WalletAdminAdjustRequest,
)
from app.services.wallet_service import (
    get_wallet,
    recharge_wallet,
    admin_adjust_wallet,
    list_transactions,
    get_wallet_by_franchise,
)

router = APIRouter(prefix="/wallet", tags=["Wallet"])


# ── Franchise: view own wallet balance ────────────────────────────────────


@router.get("", response_model=WalletOut)
async def get_wallet_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("wallet:view")),
):
    return await get_wallet(db, current_user)


# ── Franchise: recharge own wallet ────────────────────────────────────────


@router.post("/recharge", response_model=WalletTransactionOut, status_code=201)
async def recharge_wallet_endpoint(
    data: WalletRechargeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("wallet:recharge")),
):
    return await recharge_wallet(db, data, current_user)


# ── Franchise: list own wallet transactions ───────────────────────────────


@router.get("/transactions", response_model=WalletTransactionListResponse)
async def list_transactions_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    type: Optional[str] = Query(None, description="Filter by type: credit or debit"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("wallet:view")),
):
    return await list_transactions(
        db, current_user,
        page=page, limit=limit,
        txn_type=type, order_id=order_id,
        date_from=date_from, date_to=date_to,
    )


# ── Admin: view any franchise wallet ──────────────────────────────────────


@router.get("/franchise/{franchise_id}", response_model=WalletOut)
async def get_franchise_wallet_endpoint(
    franchise_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("wallet:manage")),
):
    return await get_wallet_by_franchise(db, franchise_id)


# ── Admin: credit/debit adjustment ────────────────────────────────────────


@router.post("/adjust", response_model=WalletTransactionOut, status_code=201)
async def admin_adjust_wallet_endpoint(
    data: WalletAdminAdjustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("wallet:manage")),
):
    return await admin_adjust_wallet(
        db,
        franchise_id=data.franchise_id,
        amount=data.amount,
        txn_type=data.type.value,
        description=data.description,
    )
