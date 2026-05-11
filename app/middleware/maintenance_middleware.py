from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.webconfiguration import WebConfiguration


class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(WebConfiguration))
            config = result.scalars().first()
            if config and config.maintenance_mode:
                return JSONResponse(status_code=503,content={"detail":"System under maintenance"})
        response = await call_next(request)
        return response