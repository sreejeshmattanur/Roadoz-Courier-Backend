from jose import jwt, JWTError
from fastapi import WebSocket, HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def verify_websocket_token(token: str, db: AsyncSession | None = None):
    """
    Decode the JWT and return a dict with user_id, user_type, and permissions.

    user_type values:
      - "user"      → admin / staff (User table)
      - "auth_user" → end-customer  (AuthUser table)

    If the token already carries a 'user_type' field (User tokens do),
    we trust it directly. Otherwise we fall back to DB lookup when a db
    session is provided.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid Token")

    user_id: str | None = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid Token: missing user_id")

    # Admin / staff tokens embed user_type explicitly
    user_type: str | None = payload.get("user_type")
    permissions: list[str] = list(payload.get("permissions") or [])

    if user_type is None:
        # AuthUser tokens don't carry user_type; detect via DB lookup
        if db is not None:
            from app.models.consigeeauth import AuthUser
            from app.models.user import User

            auth_result = await db.execute(
                select(AuthUser).where(AuthUser.id == user_id)
            )
            if auth_result.scalar_one_or_none():
                user_type = "auth_user"
            else:
                user_result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                if user_result.scalar_one_or_none():
                    user_type = "user"

        # Final fallback: treat as auth_user (customer) if still unknown
        if user_type is None:
            user_type = "auth_user"

    return {
        "user_id": user_id,
        "user_type": user_type,
        "permissions": permissions,
    }