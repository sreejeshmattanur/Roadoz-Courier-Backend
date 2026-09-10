from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import init_db
from app.core.security import get_password_hash
from app.middleware.auth_middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.routes import auth, franchise, orderreview,projectreview , profile, websocket, rbac, order, remittance, invoice,warehouse
from app.middleware.auth_middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware, ActivityLoggingMiddleware
from app.routes import auth, franchise, profile, websocket, rbac, order, remittance, invoice,warehouse, activity_log,consigeeauth,coningeereview,webconfiguration,notification
from app.routes import auth, franchise, profile, websocket, rbac, order, remittance, invoice,warehouse, activity_log,consigeeauth,coningeereview,webconfiguration, analytics,user_admincommunication, rate_calculator, reports, prints, operations, location
from app.routes import bulk_order, bag,label,user_franchise,consigeeuserorder, month_end_closing
from app.routes import franchise_orders
from app.routes import parcel_order as parcel_order_routes
from app.routes import pickup_assignment as pickup_assignment_routes
from app.routes import delivery_assignment as delivery_assignment_routes
from app.routes import parcel_tripsheet as parcel_tripsheet_routes

from app.routes import public as public_routes
from app.modules.fleet.routes import mobile as fleet_mobile
from app.modules.fleet.routes.driver_runtime import router as fleet_driver_runtime
from app.modules.fleet.routes import admin as fleet_admin
from app.modules.fleet.routes import fleet_management
from app.models.activity_log import ActivityLog
from app.middleware.maintenance_middleware import MaintenanceMiddleware


from app.websocket.user_admin_chat import router as websocket_router

from app.websocket.notification_socket import router as ws_router

from app.websocket.trip_sheet_socket import router as trip_sheet_ws_router
from app.websocket.driver_socket import router as driver_ws_router


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_super_admin():
    """Create the super admin user if it doesn't already exist."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.role import Role
    from app.models.user_role import UserRole
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        role_result = await db.execute(select(Role).where(Role.name == "super_admin"))
        super_admin_role = role_result.scalar_one_or_none()
        if not super_admin_role:
            super_admin_role = Role(id=str(uuid.uuid4()), name="super_admin")
            db.add(super_admin_role)
            await db.flush()

        result = await db.execute(select(User).where(User.email == settings.SUPER_ADMIN_EMAIL))
        admin = result.scalar_one_or_none()
        if not admin:
            admin = User(
                id=str(uuid.uuid4()),
                name=settings.SUPER_ADMIN_NAME,
                email=settings.SUPER_ADMIN_EMAIL,
                password_hash=get_password_hash(settings.SUPER_ADMIN_PASSWORD),
            )
            db.add(admin)

        # Ensure admin has super_admin role assigned
        user_role_result = await db.execute(select(UserRole).where(UserRole.user_id == admin.id))
        mapping = user_role_result.scalar_one_or_none()
        if not mapping:
            db.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))
        else:
            mapping.role_id = super_admin_role.id

        await db.commit()
        logger.info(f"Super admin ensured: {settings.SUPER_ADMIN_EMAIL}")


# ── Default permission definitions (module, action, description) ───────────
DEFAULT_PERMISSIONS = [
    # Users
    ("users", "create", "Create users"),
    ("users", "view", "View users list"),
    ("users", "edit", "Edit user details"),
    ("users", "delete", "Delete users"),
    # Roles
    ("roles", "create", "Create roles"),
    ("roles", "view", "View roles"),
    ("roles", "edit", "Edit roles"),
    ("roles", "delete", "Delete roles"),
    # Permissions
    ("permissions", "create", "Create permissions"),
    ("permissions", "view", "View permissions"),
    ("permissions", "edit", "Edit permissions"),
    ("permissions", "delete", "Delete permissions"),
    # User-role assignment
    ("user_roles", "assign", "Assign role to user"),
    # Franchises
    ("franchises", "create", "Create franchises"),
    ("franchises", "view", "View franchises"),
    ("franchises", "edit", "Edit franchises"),
    ("franchises", "delete", "Delete franchises"),
    # Profile
    ("profile", "view", "View own profile"),
    ("profile", "edit", "Edit own profile"),
    # Orders
    ("orders", "create", "Create orders"),
    ("orders", "view", "View orders"),
    # Pickup Addresses
    ("pickup_addresses", "create", "Create pickup addresses"),
    ("pickup_addresses", "view", "View pickup addresses"),
    # Consignees
    ("consignees", "create", "Create consignees"),
    ("consignees", "view", "View consignees"),
    ("consignees", "edit", "Edit consignees"),
    ("consignees", "delete", "Delete consignees"),

    # Remittances
    ("remittances", "view", "View remittance transactions and summary"),
    ("remittances", "manage", "Admin: create and mark remittances"),
    # Invoices
    ("invoices", "view", "View invoices"),
    ("invoices", "generate", "Admin: generate and manage invoices"),
     ("invoices", "delete", "Admin: delete and manage invoices"),
    # Activity Logs
    ("activity_logs", "view", "View activity logs"),
    # Additional Missing Permissions
    ("orders", "edit", "Edit orders"),
    ("orders", "delete", "Delete orders"),
    ("bags", "view", "View bags"),
    ("bags", "manage", "Manage bags"),
    ("warehouse", "view", "View warehouse addresses"),
    ("warehouse", "edit", "Edit warehouse addresses"),
    ("warehouse", "delete", "Delete warehouse addresses"),
    ("warehouse", "create", "Create warehouse addresses"),
    ("webconfig", "view", "View web configuration"),
    ("webconfig", "edit", "Edit web configuration"),
    ("reviews", "view", "View reviews"),
    ("reviews", "create", "Create reviews"),
    ("reviews", "edit", "Edit reviews"),
    ("reviews", "delete", "Delete reviews"),
    ("reviews", "approve", "Approve reviews"),
    ("tickets", "view", "View tickets"),
    ("tickets", "create", "Create tickets"),
    ("communication", "view", "View communications"),
    ("communication", "send", "Send messages in communication chat"),
    # Month End Closing
    ("month_end_closing", "submit", "Submit month end closing payments"),
    ("month_end_closing", "view", "View month end closing records"),
    ("month_end_closing", "approve", "Approve month end closing payments"),

    ("reset", "location", "Reset warehouse or franchise location"),
    # Fleet Drivers Management
    ("drivers", "create", "Create drivers"),
    ("drivers", "update", "Update drivers"),
    ("drivers", "delete", "Delete drivers"),
    ("drivers", "view", "View drivers"),
    ("drivers", "approve", "Approve driver applications"),
    ("drivers", "reject", "Reject driver applications"),
     # Fleet Vehicle Management
    ("vehicle", "create", "Create vehicles"),
    ("vehicle", "view", "View vehicles"),
    ("vehicle", "update", "Update vehicles"),
    ("vehicle", "delete", "Delete vehicles"),
    
    # Trip Sheets
    ("tripsheet", "create", "Create trip sheets"),
    ("tripsheet", "view", "View trip sheets"),
    ("tripsheet", "update", "Update trip sheets"),
    ("tripsheet", "delete", "Delete trip sheets"),
    # Pickup Assignment
    ("pickup_assignment", "create", "Create pickup assignments"),
    ("pickup_assignment", "view", "View pickup assignments"),
    # Delivery Assignment
    ("delivery_assignment", "create", "Create delivery assignments"),
    ("delivery_assignment", "view", "View delivery assignments"),
    
    # user orders 
    ("user_orders", "approve", "Approve orders"),
    ("user_orders", "reject", "Reject orders"), 
    
    # parcel order
    ("parcel", "create", "parcel orders"),
    ("parcel", "view", "parcel orders"),  
    ("parcel", "edit", "parcel orders"),
    ("parcel", "delete", "parcel orders"),   
    
    
    ("parcelorder", "create", "parcel orders"),
    ("parcelorder", "view", "parcel orders"),  
    ("parcelorder", "edit", "parcel orders"),
    ("parcelorder", "delete", "parcel orders"),
    
    
    # parcel sender address
    ("parcelsenders", "create", "parcel sender address"),
    ("parcelsenders", "view", "parcel sender address"),  
    ("parcelsenders", "edit", "parcel sender address"),
    ("parcelsenders", "delete", "parcel sender address"),
    
    # parcel sender address
    ("receiverparcel", "create", "parcel receiver address"),
    ("receiverparcel", "view", "parcel receiver address"),  
    ("receiverparcel", "edit", "parcel receiver address"),
    ("receiverparcel", "delete", "parcel receiver address"),
    ]


async def _seed_permissions():
    """Seed the default permissions if they don't exist."""
    from app.core.database import AsyncSessionLocal
    from app.models.permission import Permission
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        for module, action, description in DEFAULT_PERMISSIONS:
            code = f"{module}:{action}"
            result = await db.execute(select(Permission).where(Permission.code == code))
            if not result.scalar_one_or_none():
                db.add(Permission(
                    id=str(uuid.uuid4()),
                    code=code,
                    module=module,
                    action=action,
                    description=description,
                ))
        await db.commit()
        logger.info("Default permissions seeded")


# Permissions every role should have automatically
UNIVERSAL_PERMISSIONS = ["profile:view", "profile:edit"]


async def _seed_default_role_permissions():
    """Ensure every role has profile:view and profile:edit permissions."""
    from app.core.database import AsyncSessionLocal
    from app.models.role import Role
    from app.models.permission import Permission
    from app.models.role_permission import RolePermission
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        # Fetch all roles
        roles = (await db.execute(select(Role))).scalars().all()

        # Fetch the universal permission rows
        perm_result = await db.execute(
            select(Permission).where(Permission.code.in_(UNIVERSAL_PERMISSIONS))
        )
        permissions = perm_result.scalars().all()

        for role in roles:
            for perm in permissions:
                # Check if mapping already exists
                exists = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not exists.scalar_one_or_none():
                    db.add(RolePermission(
                        id=str(uuid.uuid4()),
                        role_id=role.id,
                        permission_id=perm.id,
                    ))
                    logger.info(f"Linked {perm.code} -> role '{role.name}'")

        await db.commit()
        logger.info("Default role permissions seeded")


FLEET_ADMIN_PERMISSIONS = ["fleet:drivers:view", "fleet:drivers:approve"]


async def _seed_driver_role():
    """Ensure driver role exists and super_admin has fleet admin permissions."""
    from app.core.database import AsyncSessionLocal
    from app.models.role import Role
    from app.models.permission import Permission
    from app.models.role_permission import RolePermission
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        driver_role = (
            await db.execute(
                select(Role).where(
                    Role.name == "driver",
                    Role.franchise_id.is_(None),
                    Role.warehouse_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not driver_role:
            driver_role = Role(id=str(uuid.uuid4()), name="driver")
            db.add(driver_role)
            await db.flush()
            logger.info("Driver role seeded")

        super_admin_role = (
            await db.execute(
                select(Role).where(
                    Role.name == "super_admin",
                    Role.franchise_id.is_(None),
                    Role.warehouse_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if super_admin_role:
            for code in FLEET_ADMIN_PERMISSIONS:
                perm = (await db.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
                if not perm:
                    continue
                exists = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == super_admin_role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not exists.scalar_one_or_none():
                    db.add(
                        RolePermission(
                            id=str(uuid.uuid4()),
                            role_id=super_admin_role.id,
                            permission_id=perm.id,
                        )
                    )
                    logger.info(f"Linked {code} -> role 'super_admin'")

        await db.commit()
        logger.info("Driver role and fleet admin permissions ensured")


import asyncio
from datetime import datetime, timedelta
from app.core.database import AsyncSessionLocal
from sqlalchemy import delete
from app.models.activity_log import ActivityLog

ACTIVITY_LOG_RETENTION_DAYS = 7

async def _cleanup_activity_logs():
    """Background task to delete expired activity logs."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                expiry_cutoff = datetime.utcnow() - timedelta(days=ACTIVITY_LOG_RETENTION_DAYS)
                await db.execute(delete(ActivityLog).where(ActivityLog.created_at < expiry_cutoff))
                await db.commit()
        except Exception as e:
            logger.error(f"Error cleaning up activity logs: {e}")
        # Run cleanup every 24 hours
        await asyncio.sleep(86400)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    # init_db auto-creates all tables (works for SQLite out of the box)
    await init_db()
    await _seed_permissions()
    await _seed_super_admin()
    await _seed_default_role_permissions()
    await _seed_driver_role()
    
    # Start background tasks
    cleanup_task = asyncio.create_task(_cleanup_activity_logs())
    
    yield
    logger.info("Shutting down")
    cleanup_task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## FastAPI JWT Authentication & Franchise Management System

### Features
- **Unified login** for Super Admin and Franchise users
- **JWT authentication** with access & refresh tokens
- **Franchise CRUD** with pagination and search
- **OTP verification** via SMTP email or Twilio SMS
- **Redis caching** for sessions, OTPs, and franchise data
- **WebSocket** real-time notifications at `/ws/notifications`
- **Role-based access control** (Super Admin / Franchise)
- **SQLite** by default — swap `DATABASE_URL` for PostgreSQL in production
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    from app.modules.fleet.mobile_errors import is_mobile_fleet_path, mobile_error_response

    if is_mobile_fleet_path(request.url.path):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return mobile_error_response(exc.status_code, message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from app.modules.fleet.mobile_errors import is_mobile_fleet_path, mobile_error_response, validation_error_message

    errors = jsonable_encoder(exc.errors())
    if is_mobile_fleet_path(request.url.path):
        return mobile_error_response(422, validation_error_message(errors))
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    from app.modules.fleet.mobile_errors import is_mobile_fleet_path, mobile_error_response

    logger.exception("IntegrityError", exc_info=exc)
    if is_mobile_fleet_path(request.url.path):
        return mobile_error_response(409, "Database constraint violated")
    return JSONResponse(status_code=409, content={"detail": "Database constraint violated"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    from app.modules.fleet.mobile_errors import is_mobile_fleet_path, mobile_error_response

    logger.exception("Unhandled exception", exc_info=exc)
    if is_mobile_fleet_path(request.url.path):
        return mobile_error_response(500, "Internal server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

from fastapi.staticfiles import StaticFiles

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ── Middleware ───────────────────────────────────────────────────────────────


DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
    "https://www.roadozcourier.com",
    "https://roadozcourier.com",
    "https://admin.roadozcourier.com",
    "https://staging.roadozcourier.com",
    "https://staging-admin.roadozcourier.com",
    "https://roadoz-frontend-prod.vercel.app",
]

all_origins = set(DEFAULT_ORIGINS)
for origin in settings.allowed_origins_list:
    if origin and origin.strip():
        all_origins.add(origin.strip())

origins = list(all_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ActivityLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MaintenanceMiddleware)


# ── Routers ──────────────────────────────────────────────────────────────────

API_PREFIX = "/api/v1"
app.include_router(auth.router,      prefix=API_PREFIX)
app.include_router(public_routes.router, prefix=API_PREFIX)
app.include_router(franchise.router, prefix=API_PREFIX)
app.include_router(profile.router,   prefix=API_PREFIX)
app.include_router(rbac.router,      prefix=API_PREFIX)
app.include_router(order.router,    prefix=API_PREFIX)

app.include_router(remittance.router, prefix=API_PREFIX)
app.include_router(invoice.router,   prefix=API_PREFIX)
app.include_router(activity_log.router, prefix=API_PREFIX)
app.include_router(warehouse.router,prefix=API_PREFIX)
app.include_router(projectreview.router,prefix=API_PREFIX)
app.include_router(consigeeauth.router,prefix=API_PREFIX)
app.include_router(coningeereview.router,prefix=API_PREFIX)
app.include_router(webconfiguration.router,prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(ws_router,prefix=API_PREFIX)
app.include_router(notification.router,prefix=API_PREFIX)
# app.include_router(websocket_router,prefix=API_PREFIX)
app.include_router(websocket_router, prefix=API_PREFIX)
app.include_router(user_admincommunication.router,prefix=API_PREFIX)
app.include_router(rate_calculator.router,prefix=API_PREFIX)
app.include_router(reports.router,prefix=API_PREFIX)
app.include_router(prints.router,prefix=API_PREFIX)
app.include_router(operations.router,prefix=API_PREFIX)
app.include_router(trip_sheet_ws_router,prefix=API_PREFIX)
app.include_router(bulk_order.router,prefix=API_PREFIX)
app.include_router(bag.router,prefix=API_PREFIX)
app.include_router(label.router,prefix=API_PREFIX)
app.include_router(user_franchise.router,prefix=API_PREFIX)
app.include_router(consigeeuserorder.router,prefix=API_PREFIX)
app.include_router(month_end_closing.router,prefix=API_PREFIX)
app.include_router(pickup_assignment_routes.router, prefix=API_PREFIX)
app.include_router(delivery_assignment_routes.router, prefix=API_PREFIX)
app.include_router(franchise_orders.router, prefix=API_PREFIX)

app.include_router(fleet_mobile.router)
app.include_router(fleet_driver_runtime)
app.include_router(driver_ws_router, prefix=API_PREFIX)
app.include_router(fleet_admin.router, prefix="/api/v1/int/fleet")
app.include_router(fleet_management.router, prefix=API_PREFIX)

app.include_router(location.router,prefix=API_PREFIX)
app.include_router(parcel_order_routes.router, prefix=API_PREFIX)
app.include_router(parcel_tripsheet_routes.router, prefix=API_PREFIX)



@app.get("/", tags=["Health"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "database": "SQLite (franchise.db)" if settings.DATABASE_URL.startswith("sqlite") else "PostgreSQL",
    }    


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
