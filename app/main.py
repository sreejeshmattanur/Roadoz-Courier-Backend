from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import init_db
from app.core.security import get_password_hash
from app.middleware.auth_middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.routes import auth, franchise, profile, websocket, rbac, order, wallet, remittance, invoice,warehouse

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
    # Wallet
    ("wallet", "view", "View own wallet balance and transactions"),
    ("wallet", "recharge", "Recharge own wallet"),
    ("wallet", "manage", "Admin: view/adjust any franchise wallet"),
    # Remittances
    ("remittances", "view", "View remittance transactions and summary"),
    ("remittances", "manage", "Admin: create and mark remittances"),
    # Invoices
    ("invoices", "view", "View invoices"),
    ("invoices", "generate", "Admin: generate and manage invoices"),
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    # init_db auto-creates all tables (works for SQLite out of the box)
    await init_db()
    await _seed_permissions()
    await _seed_super_admin()
    await _seed_default_role_permissions()
    yield
    logger.info("Shutting down")


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
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    logger.exception("IntegrityError", exc_info=exc)
    return JSONResponse(status_code=409, content={"detail": "Database constraint violated"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

from fastapi.staticfiles import StaticFiles

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ── Middleware ───────────────────────────────────────────────────────────────


origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://admin.roadozcourier.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)


# ── Routers ──────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"
app.include_router(auth.router,      prefix=API_PREFIX)
app.include_router(franchise.router, prefix=API_PREFIX)
app.include_router(profile.router,   prefix=API_PREFIX)
app.include_router(rbac.router,      prefix=API_PREFIX)
app.include_router(order.router,    prefix=API_PREFIX)
app.include_router(wallet.router,   prefix=API_PREFIX)
app.include_router(remittance.router, prefix=API_PREFIX)
app.include_router(invoice.router,   prefix=API_PREFIX)
app.include_router(websocket.router)
app.include_router(warehouse.router)


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
