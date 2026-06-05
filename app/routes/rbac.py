from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from app.core.database import get_db
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User
from app.schemas.rbac_user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserOut,
    UserListResponse,
    AssignRoleRequest,
)
from app.schemas.rbac_role import (
    RoleCreateRequest,
    RoleUpdateRequest,
    RoleWithPermissionsOut,
    RoleListResponse,
)
from app.schemas.rbac_permission import (
    PermissionCreateRequest,
    PermissionUpdateRequest,
    PermissionOut,
)
from app.services.rbac_service import (
    create_user,
    list_users,
    update_user,
    delete_user,
    create_role,
    list_roles,
    get_role,
    update_role,
    delete_role,
    create_permission,
    list_permissions,
    update_permission,
    delete_permission,
    assign_role_to_user,
)

router = APIRouter(prefix="/rbac", tags=["RBAC"])


# -------------------- Users --------------------


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user_endpoint(
    data: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("users:create")),
):
    return await create_user(db, data, current_user)










# @router.get("/users", response_model=UserListResponse)
# async def list_users_endpoint(
#     page: int = Query(1, ge=1),
#     start_date: Optional[date] = Query(None,description="Start date"),
#     end_date: Optional[date] = Query(None,description="End date"),
#     limit: int = Query(10, ge=1, le=100),
#     search: Optional[str] = Query(None, description="Search by name, email, phone, or employee code"),
#     franchise_id: Optional[str] = Query(None, description="Filter by franchise ID (super_admin only)"),
#     role: Optional[str] = Query(None, description="Filter by role name"),
#     assigned_by: Optional[str] = Query(None, description="Filter by who assigned the role (user ID)"),
#     assigned_by_me: Optional[bool] = Query(None, description="Show only users whose role was assigned by me"),
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
#     _: User = Depends(require_permission("users:view")),
# ):
#     effective_assigned_by = assigned_by
#     if assigned_by_me:
#         effective_assigned_by = current_user.id
#     return await list_users(db, current_user, page=page, limit=limit, search=search, franchise_id=franchise_id, role=role, assigned_by=effective_assigned_by)

@router.get("/users",response_model=UserListResponse)
async def list_users_endpoint(
    page: int = Query(1, ge=1),
    start_date: Optional[date] = Query(None,description="Start date"),
    end_date: Optional[date] = Query(None,description="End date"),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None,description="Search by name, email, phone, or employee code"),
    franchise_id: Optional[str] = Query(None,description="Filter by franchise ID (super_admin only)"),
    role: Optional[str] = Query(None,description="Filter by role name"),
    assigned_by: Optional[str] = Query(None,description="Filter by who assigned the role (user ID)"),
    assigned_by_me: Optional[bool] = Query(None,description="Show only users whose role was assigned by me"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("users:view")),):
    effective_assigned_by = assigned_by
    if assigned_by_me:
        effective_assigned_by = current_user.id
    return await list_users(
        db=db,
        current_user=current_user,
        page=page,
        limit=limit,
        search=search,
        franchise_id=franchise_id,
        role=role,
        assigned_by=effective_assigned_by,
        start_date=start_date,
        end_date=end_date,
    )











@router.put("/users/{user_id}", response_model=UserOut)
async def update_user_endpoint(
    user_id: str,
    data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("users:edit")),
):
    return await update_user(db, user_id, data, current_user)


@router.delete("/users/{user_id}")
async def delete_user_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("users:delete")),
):
    return await delete_user(db, user_id, current_user)


# -------------------- Roles --------------------


@router.post("/roles", response_model=RoleWithPermissionsOut, status_code=201)
async def create_role_endpoint(
    data: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: User = Depends(require_permission("roles:create")),
):
    return await create_role(db, data, current_user)


@router.get("/roles", response_model=RoleListResponse)
async def list_roles_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    franchise_id: Optional[str] = Query(None, description="Filter by franchise ID (super_admin only)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: User = Depends(require_permission("roles:view")),
):
    return await list_roles(db, current_user, page=page, limit=limit, franchise_id=franchise_id)


@router.get("/roles/{role_id}", response_model=RoleWithPermissionsOut)
async def get_role_endpoint(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: User = Depends(require_permission("roles:view")),
):
    return await get_role(db, role_id, current_user)


@router.put("/roles/{role_id}", response_model=RoleWithPermissionsOut)
async def update_role_endpoint(
    role_id: str,
    data: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: User = Depends(require_permission("roles:edit")),
):
    return await update_role(db, role_id, data, current_user)


@router.delete("/roles/{role_id}")
async def delete_role_endpoint(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: User = Depends(require_permission("roles:delete")),
):
    return await delete_role(db, role_id, current_user)


# -------------------- Permissions --------------------


@router.post("/permissions", response_model=PermissionOut, status_code=201)
async def create_permission_endpoint(
    data: PermissionCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("permissions:create")),
):
    return await create_permission(db, data)


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("permissions:view")),
):
    return await list_permissions(db)


@router.put("/permissions/{permission_id}", response_model=PermissionOut)
async def update_permission_endpoint(
    permission_id: str,
    data: PermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("permissions:edit")),
):
    return await update_permission(db, permission_id, data)


@router.delete("/permissions/{permission_id}")
async def delete_permission_endpoint(
    permission_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("permissions:delete")),
):
    return await delete_permission(db, permission_id)


# -------------------- Assign role --------------------


@router.post("/assign-role")
async def assign_role_endpoint(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("user_roles:assign")),
):
    return await assign_role_to_user(db, data.user_id, data.role_id, current_user)
