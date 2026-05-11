from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging
import time
import uuid
from app.utils.jwt import decode_token
from app.core.database import AsyncSessionLocal
from app.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)

# Routes that do NOT require authentication
PUBLIC_ROUTES = {
    "/api/v1/auth/login",
    "/api/v1/auth/send-otp",
    "/api/v1/auth/verify-otp",
    "/api/v1/auth/refresh",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/",
    "/ws/notifications",
    "/websocket/ws/notifications", 
}


def _is_websocket(request: Request) -> bool:
    return request.headers.get("upgrade", "").lower() == "websocket"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request with timing information."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_websocket(request):                      # ← ADD THIS
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} ({duration:.1f}ms)"
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

import re
from starlette.routing import Match

def _get_activity_description(request: Request) -> str:
    # Try to match the exact FastAPI route
    try:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                # FastAPI auto-generates 'summary' from the function name or explicit decorator kwargs
                summary = getattr(route, "summary", "")
                name = getattr(route, "name", "")
                
                # If the developer explicitly added a docstring or summary, it's often capitalized nicely.
                # If they didn't, name is the function name (e.g. create_consignee_endpoint).
                if name:
                    clean_name = name.replace("_", " ").strip()
                    if clean_name.endswith(" endpoint"):
                        clean_name = clean_name[:-9].strip()
                    return clean_name.capitalize()
                
                if summary:
                    return summary
    except Exception:
        pass
        
    # Fallback to URL parsing if route mapping fails
    path = request.url.path
    method = request.method
    
    if "/auth/login" in path:
        return "User logged in"
    
    base_path = path.replace("/api/v1/", "").strip("/")
    parts = base_path.split("/")
    
    # Filter out UUIDs and numeric IDs
    entity_parts = [p for p in parts if not re.match(r'^[0-9a-fA-F-]{10,}$|^\d+$', p)]
    
    if entity_parts:
        entity = entity_parts[-1]
        if entity.endswith('ies'):
            entity = entity[:-3] + 'y'
        elif entity.endswith('sses'):
            entity = entity[:-2]
        elif entity.endswith('s') and not entity.endswith('ss'):
            entity = entity[:-1]
        module = entity.replace('-', ' ')
    else:
        module = "resource"
    
    if method == "POST":
        action = "Created"
    elif method in ["PUT", "PATCH"]:
        action = "Updated"
    elif method == "DELETE":
        action = "Deleted"
    else:
        action = "Modified"
        
    return f"{action} {module}"

class ActivityLoggingMiddleware(BaseHTTPMiddleware):
    """Log write operations to the database."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_websocket(request):                      # ← ADD THIS
            return await call_next(request)
        response = await call_next(request)
        
        # Only log successful write operations
        if request.method in ["POST", "PUT", "DELETE", "PATCH"] and 200 <= response.status_code < 400:
            user_id = None
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                payload = decode_token(token)
                if payload:
                    user_id = payload.get("user_id")
            
            try:
                async with AsyncSessionLocal() as db:
                    log = ActivityLog(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        method=request.method,
                        path=request.url.path,
                        description=_get_activity_description(request),
                        ip_address=request.client.host if request.client else None
                    )
                    db.add(log)
                    await db.commit()
            except Exception as e:
                logger.error(f"Failed to log activity: {e}")
                
        return response
