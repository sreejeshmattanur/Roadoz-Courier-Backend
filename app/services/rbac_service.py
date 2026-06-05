import math
import uuid
import logging
from datetime import date
from fastapi import HTTPException, status
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime,time
from app.core.security import get_password_hash
from app.models.user import User
from app.models.franchise import Franchise
from app.models.role import Role
from app.models.permission import Permission
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
from app.schemas.rbac_user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserOut,
    UserListResponse,
    RoleInfo,
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

logger = logging.getLogger(__name__)


# -------------------- Helpers --------------------


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    r = row.scalar_one_or_none()
    return r.lower() if r else None


async def _get_franchise_for_owner(db: AsyncSession, user_id: str) -> Franchise | None:
    result = await db.execute(
        select(Franchise).where(Franchise.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _generate_employee_code(db: AsyncSession, franchise: Franchise) -> str:
    franchise.employee_counter += 1
    seq = franchise.employee_counter
    await db.flush()
    return f"{franchise.franchise_code}-E{str(seq).zfill(3)}"


async def _build_user_out(db: AsyncSession, user: User) -> UserOut:
    role_row = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    role = role_row.scalar_one_or_none()
    role_info = RoleInfo(id=role.id, name=role.name) if role else None

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        pincode=user.pincode,
        address=user.address,
        location=user.location,
        franchise_id=user.franchise_id,
        employee_code=user.employee_code,
        role=role_info,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _assert_franchise_owns_user(franchise: Franchise, target_user: User) -> None:
    if target_user.franchise_id != franchise.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage users belonging to your franchise",
        )


# -------------------- Users --------------------


async def create_user(
    db: AsyncSession, data: UserCreateRequest, current_user: User
) -> UserOut:
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    caller_role = await _get_caller_role_name(db, current_user.id)

    franchise_id = None
    employee_code = None

    if caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No franchise linked to your account",
            )
        if not franchise.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your franchise is currently inactive",
            )
        franchise_id = franchise.id
        employee_code = await _generate_employee_code(db, franchise)

    user = User(
        id=str(uuid.uuid4()),
        name=data.name,
        email=data.email,
        password_hash=get_password_hash(data.password),
        phone=data.phone,
        pincode=data.pincode,
        address=data.address,
        location=data.location,
        franchise_id=franchise_id,
        employee_code=employee_code,
        is_active=bool(data.is_active),
    )
    db.add(user)
    await db.flush()

    return await _build_user_out(db, user)












async def list_users(
    db: AsyncSession,
    current_user: User,
    page: int = 1,
    limit: int = 10,
    search: str | None = None,
    franchise_id: str | None = None,
    role: str | None = None,
    assigned_by: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> UserListResponse:

    caller_role = await _get_caller_role_name(
        db,
        current_user.id
    )

    base_filter = []

    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)

    if is_global:

        if franchise_id is not None:

            if franchise_id == "none":
                base_filter.append(
                    User.franchise_id.is_(None)
                )

            else:
                base_filter.append(
                    User.franchise_id == franchise_id
                )

    elif caller_role == "franchise":

        franchise = await _get_franchise_for_owner(
            db,
            current_user.id
        )

        if not franchise:
            return UserListResponse(
                items=[],
                total=0,
                page=page,
                limit=limit,
                pages=0,
            )

        base_filter.append(
            User.franchise_id == franchise.id
        )

    else:

        if current_user.franchise_id:

            base_filter.append(
                User.franchise_id == current_user.franchise_id
            )

        else:

            base_filter.append(
                User.id == current_user.id
            )

    query = (
        select(User)
        .order_by(
            User.created_at.desc(),
            User.id.desc()
        )
    )

    count_query = select(func.count()).select_from(User)

    if role:

        query = query.join(
            UserRole,
            UserRole.user_id == User.id
        )

        count_query = count_query.join(
            UserRole,
            UserRole.user_id == User.id
        )

        query = query.join(
            Role,
            Role.id == UserRole.role_id
        ).where(
            Role.name == role
        )

        count_query = count_query.join(
            Role,
            Role.id == UserRole.role_id
        ).where(
            Role.name == role
        )

        if assigned_by:

            query = query.where(
                UserRole.assigned_by == assigned_by
            )

            count_query = count_query.where(
                UserRole.assigned_by == assigned_by
            )

    elif assigned_by:

        query = query.outerjoin(
            UserRole,
            UserRole.user_id == User.id
        )

        count_query = count_query.outerjoin(
            UserRole,
            UserRole.user_id == User.id
        )

        query = query.where(
            UserRole.assigned_by == assigned_by
        )

        count_query = count_query.where(
            UserRole.assigned_by == assigned_by
        )

    for f in base_filter:

        query = query.where(f)
        count_query = count_query.where(f)

    if search:

        search_filter = or_(
            User.name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
            User.phone.ilike(f"%{search}%"),
            User.employee_code.ilike(f"%{search}%"),
        )

        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # START DATE FILTER
    if start_date:

        start_datetime = datetime.combine(
            start_date,
            time.min
        )

        query = query.where(
            User.created_at >= start_datetime
        )

        count_query = count_query.where(
            User.created_at >= start_datetime
        )

    # END DATE FILTER
    if end_date:

        end_datetime = datetime.combine(
            end_date,
            time.max
        )

        query = query.where(
            User.created_at <= end_datetime
        )

        count_query = count_query.where(
            User.created_at <= end_datetime
        )

    total = (
        await db.execute(count_query)
    ).scalar_one()

    offset = (page - 1) * limit

    result = await db.execute(
        query.offset(offset).limit(limit)
    )

    users = result.scalars().all()

    items = [
        await _build_user_out(db, u)
        for u in users
    ]

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit)
        if total > 0 else 0,
    )








# async def list_users(
#     db: AsyncSession,
#     current_user: User,
#     page: int = 1,
#     limit: int = 10,
#     search: str | None = None,
#     franchise_id: str | None = None,
#     role: str | None = None,
#     assigned_by: str | None = None,
# ) -> UserListResponse:
#     caller_role = await _get_caller_role_name(db, current_user.id)

#     base_filter = []

#     if caller_role == "super_admin":
#         # Super admin can optionally filter by franchise_id
#         if franchise_id is not None:
#             if franchise_id == "none":
#                 base_filter.append(User.franchise_id.is_(None))
#             else:
#                 base_filter.append(User.franchise_id == franchise_id)
#     elif caller_role == "franchise":
#         franchise = await _get_franchise_for_owner(db, current_user.id)
#         if not franchise:
#             return UserListResponse(items=[], total=0, page=page, limit=limit, pages=0)
#         base_filter.append(User.franchise_id == franchise.id)
#     else:
#         # Employee or other role — scope to own franchise
#         if current_user.franchise_id:
#             base_filter.append(User.franchise_id == current_user.franchise_id)
#         else:
#             # No franchise association — only see themselves
#             base_filter.append(User.id == current_user.id)

#     query = select(User).order_by(User.created_at.desc(), User.id.desc())
#     count_query = select(func.count()).select_from(User)

#     # Filter by role — INNER JOIN (only users who have that role)
#     if role:
#         query = query.join(UserRole, UserRole.user_id == User.id)
#         count_query = count_query.join(UserRole, UserRole.user_id == User.id)
#         query = query.join(Role, Role.id == UserRole.role_id).where(Role.name == role)
#         count_query = count_query.join(Role, Role.id == UserRole.role_id).where(Role.name == role)
#         if assigned_by:
#             query = query.where(UserRole.assigned_by == assigned_by)
#             count_query = count_query.where(UserRole.assigned_by == assigned_by)
#     elif assigned_by:
#         # OUTER JOIN so users without roles still appear
#         query = query.outerjoin(UserRole, UserRole.user_id == User.id)
#         count_query = count_query.outerjoin(UserRole, UserRole.user_id == User.id)
#         query = query.where(UserRole.assigned_by == assigned_by)
#         count_query = count_query.where(UserRole.assigned_by == assigned_by)

#     for f in base_filter:
#         query = query.where(f)
#         count_query = count_query.where(f)

#     if search:
#         search_filter = or_(
#             User.name.ilike(f"%{search}%"),
#             User.email.ilike(f"%{search}%"),
#             User.phone.ilike(f"%{search}%"),
#             User.employee_code.ilike(f"%{search}%"),
#         )
#         query = query.where(search_filter)
#         count_query = count_query.where(search_filter)

#     total = (await db.execute(count_query)).scalar_one()
#     offset = (page - 1) * limit
#     result = await db.execute(query.offset(offset).limit(limit))
#     users = result.scalars().all()

#     items = [await _build_user_out(db, u) for u in users]

#     return UserListResponse(
#         items=items,
#         total=total,
#         page=page,
#         limit=limit,
#         pages=math.ceil(total / limit) if total > 0 else 0,
#     )

















async def update_user(
    db: AsyncSession, user_id: str, data: UserUpdateRequest, current_user: User
) -> UserOut:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
    caller_role = await _get_caller_role_name(db, current_user.id)
    if caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No franchise linked"
            )
        _assert_franchise_owns_user(franchise, user)
    elif not is_global:
        # Employee or other role — can only edit users in own franchise
        if current_user.franchise_id:
            if user.franchise_id != current_user.franchise_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only manage users in your franchise",
                )
        elif user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    return await _build_user_out(db, user)


async def delete_user(
    db: AsyncSession, user_id: str, current_user: User
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself"
        )

    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
    caller_role = await _get_caller_role_name(db, current_user.id)
    if caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No franchise linked"
            )
        _assert_franchise_owns_user(franchise, user)
    elif not is_global:
        # Employee or other role — can only delete users in own franchise
        if current_user.franchise_id:
            if user.franchise_id != current_user.franchise_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only manage users in your franchise",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )

    await db.delete(user)
    await db.flush()
    return {"message": "User deleted successfully"}


# -------------------- Roles --------------------


async def create_role(db: AsyncSession, data: RoleCreateRequest, current_user: User) -> RoleWithPermissionsOut:
    result = await db.execute(select(Role).where(Role.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role already exists")

    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
    caller_role = await _get_caller_role_name(db, current_user.id)

    franchise_id = None
    if caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No franchise linked")
        franchise_id = franchise.id
    elif not is_global:
        if current_user.franchise_id:
            franchise_id = current_user.franchise_id

    role = Role(id=str(uuid.uuid4()), name=data.name, franchise_id=franchise_id)
    db.add(role)
    await db.flush()

    if data.permission_codes:
        perms = (await db.execute(select(Permission).where(Permission.code.in_(data.permission_codes)))).scalars().all()
        found = {p.code for p in perms}
        missing = [c for c in data.permission_codes if c not in found]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown permissions: {missing}")

        for p in perms:
            db.add(RolePermission(role_id=role.id, permission_id=p.id))
        await db.flush()

    return await get_role(db, role.id)


async def list_roles(
    db: AsyncSession, current_user: User, page: int = 1, limit: int = 10, franchise_id: str | None = None
) -> RoleListResponse:
    base_filter = [Role.name != "super_admin"]

    caller_role = await _get_caller_role_name(db, current_user.id)
    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)

    if is_global:
        if franchise_id is not None:
            if franchise_id == "none":
                base_filter.append(Role.franchise_id.is_(None))
            else:
                base_filter.append(Role.franchise_id == franchise_id)
        else:
            base_filter.append(Role.franchise_id.is_(None))
    elif caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            return RoleListResponse(items=[], total=0, page=page, limit=limit, pages=0)
        base_filter.append(Role.franchise_id == franchise.id)
    else:
        if current_user.franchise_id:
            base_filter.append(Role.franchise_id == current_user.franchise_id)

    query = select(Role)
    count_query = select(func.count()).select_from(Role)

    for f in base_filter:
        query = query.where(f)
        count_query = count_query.where(f)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(Role.created_at.desc())
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    roles = result.scalars().all()

    items = []
    for r in roles:
        items.append(await get_role(db, r.id))

    return RoleListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total > 0 else 0,
    )


async def get_role(db: AsyncSession, role_id: str, current_user: User = None) -> RoleWithPermissionsOut:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
    if current_user:
        is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
        caller_role = await _get_caller_role_name(db, current_user.id)
        if not is_global:
            my_franchise_id = None
            if caller_role == "franchise":
                f = await _get_franchise_for_owner(db, current_user.id)
                if f: my_franchise_id = f.id
            else:
                my_franchise_id = current_user.franchise_id
            
            if role.franchise_id != my_franchise_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view roles belonging to your franchise")
        
    if role.name.lower() == "super_admin":
        # Never allow viewing super_admin via direct API access, even if global
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    perm_rows = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
        .where(Permission.is_active.is_(True))
    )
    permissions = [r[0] for r in perm_rows.all()]

    return RoleWithPermissionsOut(
        id=role.id,
        name=role.name,
        is_active=role.is_active,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=permissions,
    )


async def update_role(db: AsyncSession, role_id: str, data: RoleUpdateRequest, current_user: User = None) -> RoleWithPermissionsOut:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
    if current_user:
        is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
        caller_role = await _get_caller_role_name(db, current_user.id)
        if not is_global:
            my_franchise_id = None
            if caller_role == "franchise":
                f = await _get_franchise_for_owner(db, current_user.id)
                if f: my_franchise_id = f.id
            else:
                my_franchise_id = current_user.franchise_id
            
            if role.franchise_id != my_franchise_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify roles belonging to your franchise")
        else:
            if role.franchise_id is not None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global users cannot modify franchise roles")

    if role.name.lower() == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify the super_admin role",
        )

    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data:
        role.name = update_data["name"]
    if "is_active" in update_data:
        role.is_active = bool(update_data["is_active"])

    if "permission_codes" in update_data and update_data["permission_codes"] is not None:
        codes = update_data["permission_codes"]
        perms = (await db.execute(select(Permission).where(Permission.code.in_(codes)))).scalars().all()
        found = {p.code for p in perms}
        missing = [c for c in codes if c not in found]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown permissions: {missing}")

        await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for p in perms:
            db.add(RolePermission(role_id=role.id, permission_id=p.id))

    await db.flush()
    return await get_role(db, role.id)


async def delete_role(db: AsyncSession, role_id: str, current_user: User = None) -> dict:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
    if current_user:
        is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)
        caller_role = await _get_caller_role_name(db, current_user.id)
        if not is_global:
            my_franchise_id = None
            if caller_role == "franchise":
                f = await _get_franchise_for_owner(db, current_user.id)
                if f: my_franchise_id = f.id
            else:
                my_franchise_id = current_user.franchise_id
            
            if role.franchise_id != my_franchise_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete roles belonging to your franchise")
        else:
            if role.franchise_id is not None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global users cannot delete franchise roles")

    if role.name.lower() in ("super_admin", "franchise"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system roles",
        )

    await db.delete(role)
    await db.flush()
    return {"message": "Role deleted successfully"}


# -------------------- Permissions --------------------


async def create_permission(db: AsyncSession, data: PermissionCreateRequest) -> PermissionOut:
    result = await db.execute(select(Permission).where(Permission.code == data.code))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission already exists")

    perm = Permission(
        id=str(uuid.uuid4()),
        code=data.code,
        module=data.module,
        action=data.action,
        description=data.description,
        is_active=bool(data.is_active),
    )
    db.add(perm)
    await db.flush()
    return PermissionOut.model_validate(perm)


async def list_permissions(db: AsyncSession) -> list[PermissionOut]:
    result = await db.execute(select(Permission).order_by(Permission.module.asc(), Permission.action.asc()))
    perms = result.scalars().all()
    return [PermissionOut.model_validate(p) for p in perms]


async def update_permission(db: AsyncSession, permission_id: str, data: PermissionUpdateRequest) -> PermissionOut:
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(perm, field, value)

    await db.flush()
    return PermissionOut.model_validate(perm)


async def delete_permission(db: AsyncSession, permission_id: str) -> dict:
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")

    await db.delete(perm)
    await db.flush()
    return {"message": "Permission deleted successfully"}


# -------------------- Assign role --------------------


async def assign_role_to_user(
    db: AsyncSession, user_id: str, role_id: str, current_user: User
) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    caller_role = await _get_caller_role_name(db, current_user.id)

    is_global = not current_user.franchise_id and not await _get_franchise_for_owner(db, current_user.id)

    # Franchise users can only assign roles to their own employees
    if caller_role == "franchise":
        franchise = await _get_franchise_for_owner(db, current_user.id)
        if not franchise:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No franchise linked"
            )
        _assert_franchise_owns_user(franchise, user)
        # Franchise cannot assign super_admin or franchise roles
        if role.name.lower() in ("super_admin", "franchise"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign system roles",
            )
    elif not is_global:
        # Employee or other role — can only assign within own franchise
        if not current_user.franchise_id or user.franchise_id != current_user.franchise_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only assign roles to users in your franchise",
            )
        if role.name.lower() in ("super_admin", "franchise"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign system roles",
            )

    existing = (await db.execute(select(UserRole).where(UserRole.user_id == user_id))).scalar_one_or_none()
    if existing:
        existing.role_id = role_id
        existing.assigned_by = current_user.id
    else:
        db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by=current_user.id))

    await db.flush()
    return {"message": "Role assigned successfully", "user_id": user_id, "role": role.name}
