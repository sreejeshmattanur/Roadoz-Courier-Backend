from jose import jwt, JWTError
from fastapi import WebSocket, HTTPException

from app.core.config import settings


async def verify_websocket_token(token: str):
    try:
        payload = jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
        return {
            "user_id": payload.get("user_id"),
            "user_type": payload.get("user_type")}
    except JWTError:

        raise HTTPException(
            status_code=401,
            detail="Invalid Token"
        )