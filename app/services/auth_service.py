from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status, Request
from app.models.user import User
from app.models.franchise import Franchise
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.permission import Permission
from app.core.security import verify_password
from app.utils.jwt import create_access_token, create_refresh_token
from app.schemas.auth import (
    LoginRequest, TokenResponse, RoleCheckResponse, RoleOut, FranchiseInfo, WarehouseInfo
)


async def _resolve_franchise(db: AsyncSession, user: User, role_name: str | None) -> Franchise | None:
    """Resolve the franchise for any user — owner or employee."""
    if not role_name:
        return None

    if role_name == "franchise":
        # User IS the franchise owner
        result = await db.execute(
            select(Franchise).where(Franchise.user_id == user.id)
        )
        return result.scalar_one_or_none()

    # User is an employee under a franchise
    if user.franchise_id:
        result = await db.execute(
            select(Franchise).where(Franchise.id == user.franchise_id)
        )
        return result.scalar_one_or_none()

    return None


async def authenticate_user(db: AsyncSession, request: LoginRequest, http_request: Request = None) -> TokenResponse:
    """Unified login with classic RBAC role+permissions context."""

    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    role_row = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    role = role_row.scalar_one_or_none()
    role_name = role.name.lower() if role else None

    franchise = None
    warehouse = None

    # Franchise-specific: require franchise_code when role name is 'franchise'
    if role_name == "franchise":
        if not request.franchise_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Franchise code is required for franchise login",
            )
        result = await db.execute(
            select(Franchise).where(
                Franchise.user_id == user.id,
                Franchise.franchise_code == request.franchise_code,
            )
        )
        franchise = result.scalar_one_or_none()
        if not franchise:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid franchise code")
        if not franchise.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Franchise account is disabled")
    elif role_name == "warehouse":
        from app.models.warehouse import WareHouseAddress
        result = await db.execute(
            select(WareHouseAddress).where(
                WareHouseAddress.user_id == user.id,
            )
        )
        warehouse = result.scalar_one_or_none()
        if not warehouse:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Warehouse account not found")
    else:
        # For employees, resolve their parent franchise
        franchise = await _resolve_franchise(db, user, role_name)

    perm_rows = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id if role else False)
        .where(Permission.is_active.is_(True))
    )
    permissions = [r[0] for r in perm_rows.all()] if role else []

    token_data = {
        "user_id": user.id,
        "email": user.email,
        "role_id": role.id if role else None,
        "role": role.name if role else None,
        "permissions": permissions,
        "franchise_id": franchise.id if franchise else None,
        "franchise_code": franchise.franchise_code if franchise else None,
        "warehouse_id": warehouse.id if warehouse else None,
        "warehouse_nickname": warehouse.nickname if warehouse else None,
        "warehouse_contact_name": warehouse.contact_name if warehouse else None,
    }

    franchise_info = None
    if franchise:
        franchise_info = FranchiseInfo(
            id=franchise.id,
            franchise_code=franchise.franchise_code,
            name=franchise.name,
        )

    warehouse_info = None
    if warehouse:
        warehouse_info = WarehouseInfo(
            id=warehouse.id,
            nickname=warehouse.nickname,
            contact_name=warehouse.contact_name,
        )

    if http_request:
        http_request.state.user_id = user.id

    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=(RoleOut(id=role.id, name=role.name) if role else None),
        permissions=permissions,
        franchise=franchise_info,
        warehouse=warehouse_info,
    )


async def get_user_role_by_email(db: AsyncSession, email: str, http_request: Request = None) -> RoleCheckResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user and http_request:
        http_request.state.user_id = user.id

    if not user:
        return RoleCheckResponse(role=None, requires_franchise_code=False)

    role_row = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    role = role_row.scalar_one_or_none()
    return RoleCheckResponse(
        role=(RoleOut(id=role.id, name=role.name) if role else None),
        requires_franchise_code=(role is not None and role.name.lower() == "franchise"),
    )
