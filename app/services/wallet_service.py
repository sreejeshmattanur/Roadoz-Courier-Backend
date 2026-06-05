import math
import uuid
import logging
from datetime import datetime, date

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.franchise import Franchise
from app.models.wallet import Wallet, WalletTransaction
from app.models.role import Role
from app.models.user_role import UserRole
from app.schemas.wallet import (
    WalletOut,
    WalletTransactionOut,
    WalletTransactionListResponse,
    WalletRechargeRequest,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    r = row.scalar_one_or_none()
    return r.lower() if r else None


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    result = await db.execute(select(Franchise).where(Franchise.user_id == user.id))
    franchise = result.scalar_one_or_none()
    return franchise.id if franchise else None


# ── Get or create wallet ─────────────────────────────────────────────────


async def get_or_create_wallet(db: AsyncSession, franchise_id: str) -> Wallet:
    result = await db.execute(
        select(Wallet).where(Wallet.franchise_id == franchise_id)
    )
    wallet = result.scalar_one_or_none()
    if wallet:
        return wallet

    wallet = Wallet(
        id=str(uuid.uuid4()),
        franchise_id=franchise_id,
        balance=0,
    )
    db.add(wallet)
    await db.flush()
    await db.refresh(wallet)
    return wallet


# ── Get wallet balance ───────────────────────────────────────────────────


async def get_wallet(db: AsyncSession, current_user: User) -> WalletOut:
    franchise_id = await _resolve_franchise_id(db, current_user)
    if not franchise_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No franchise linked to this user",
        )

    wallet = await get_or_create_wallet(db, franchise_id)
    return WalletOut.model_validate(wallet)


# ── Recharge wallet (franchise self-recharge) ────────────────────────────


async def recharge_wallet(
    db: AsyncSession, data: WalletRechargeRequest, current_user: User
) -> WalletTransactionOut:
    franchise_id = await _resolve_franchise_id(db, current_user)
    if not franchise_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No franchise linked to this user",
        )

    wallet = await get_or_create_wallet(db, franchise_id)

    opening = float(wallet.balance)
    closing = round(opening + data.amount, 2)

    wallet.balance = closing

    txn = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        order_id=None,
        amount=data.amount,
        type="credit",
        opening_balance=opening,
        closing_balance=closing,
        description=data.description or f"Wallet recharged with Rs. {data.amount}",
    )
    db.add(txn)
    await db.flush()
    await db.refresh(txn)

    logger.info(f"Wallet recharged: franchise={franchise_id}, amount={data.amount}, closing={closing}")
    return WalletTransactionOut.model_validate(txn)


# ── Admin credit/debit adjustment ────────────────────────────────────────


async def admin_adjust_wallet(
    db: AsyncSession,
    franchise_id: str,
    amount: float,
    txn_type: str,
    description: str,
) -> WalletTransactionOut:
    # Validate franchise exists
    result = await db.execute(select(Franchise).where(Franchise.id == franchise_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    wallet = await get_or_create_wallet(db, franchise_id)

    opening = float(wallet.balance)

    if txn_type == "debit":
        if opening < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient wallet balance. Current: Rs. {opening}",
            )
        closing = round(opening - amount, 2)
    else:
        closing = round(opening + amount, 2)

    wallet.balance = closing

    txn = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        order_id=None,
        amount=amount,
        type=txn_type,
        opening_balance=opening,
        closing_balance=closing,
        description=description,
    )
    db.add(txn)
    await db.flush()
    await db.refresh(txn)

    logger.info(f"Admin wallet adjust: franchise={franchise_id}, type={txn_type}, amount={amount}, closing={closing}")
    return WalletTransactionOut.model_validate(txn)


# ── Debit wallet for an order (called during order creation) ─────────────


async def debit_for_order(
    db: AsyncSession, franchise_id: str, order_id: str, shipping_charge: float
) -> WalletTransaction:
    wallet = await get_or_create_wallet(db, franchise_id)

    opening = float(wallet.balance)
    if opening < shipping_charge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient wallet balance. Required: Rs. {shipping_charge}, Available: Rs. {opening}",
        )

    closing = round(opening - shipping_charge, 2)
    wallet.balance = closing

    txn = WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        order_id=order_id,
        amount=shipping_charge,
        type="debit",
        opening_balance=opening,
        closing_balance=closing,
        description=f"Debited for order id {order_id}.",
    )
    db.add(txn)
    await db.flush()

    logger.info(f"Wallet debited: franchise={franchise_id}, order={order_id}, amount={shipping_charge}")
    return txn


# ── List wallet transactions ─────────────────────────────────────────────


async def list_transactions(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    limit: int = 25,
    txn_type: str | None = None,
    order_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> WalletTransactionListResponse:
    caller_role = await _get_caller_role_name(db, current_user.id)

    # Determine franchise scope
    from app.dependencies.role_checker import is_global_user
    if await is_global_user(db, current_user):
        # global user must have a franchise_id filter passed — handled at route level
        # For now, return all transactions
        franchise_id = None
    else:
        franchise_id = await _resolve_franchise_id(db, current_user)
        if not franchise_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No franchise linked to this user",
            )

    filters = []

    if franchise_id:
        wallet = await get_or_create_wallet(db, franchise_id)
        filters.append(WalletTransaction.wallet_id == wallet.id)

    if txn_type:
        filters.append(WalletTransaction.type == txn_type)

    if order_id:
        filters.append(WalletTransaction.order_id == order_id)

    if date_from:
        filters.append(WalletTransaction.created_at >= datetime.combine(date_from, datetime.min.time()))

    if date_to:
        filters.append(WalletTransaction.created_at <= datetime.combine(date_to, datetime.max.time()))

    query = select(WalletTransaction).order_by(WalletTransaction.created_at.desc())
    count_query = select(func.count()).select_from(WalletTransaction)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    transactions = result.scalars().all()

    return WalletTransactionListResponse(
        items=[WalletTransactionOut.model_validate(t) for t in transactions],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


# ── Get wallet for a specific franchise (admin use) ──────────────────────


async def get_wallet_by_franchise(db: AsyncSession, franchise_id: str) -> WalletOut:
    result = await db.execute(select(Franchise).where(Franchise.id == franchise_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    wallet = await get_or_create_wallet(db, franchise_id)
    return WalletOut.model_validate(wallet)
