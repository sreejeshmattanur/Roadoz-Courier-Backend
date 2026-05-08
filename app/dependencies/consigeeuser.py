from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


from app.core.database import get_db
from app.models.consigeeauth import AuthUser
from app.core.config import settings

security = HTTPBearer()
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),db: AsyncSession = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token")
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token is invalid or expired")
    result = await db.execute(
        select(AuthUser).where(AuthUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found")
    return user