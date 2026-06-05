from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import oauth2_scheme
from app.utils.jwt import verify_access_token
from app.utils.redis import is_token_blacklisted
from app.models.user import User
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.permission import Permission
from app.models.franchise import Franchise


async def is_global_user(db: AsyncSession, current_user: User) -> bool:
    if current_user.franchise_id:
        return False
    result = await db.execute(select(Franchise).where(Franchise.user_id == current_user.id))
    franchise = result.scalar_one_or_none()
    return franchise is None
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if await is_token_blacklisted(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    payload = verify_access_token(token)
    if not payload:
        raise credentials_exception

    user_id: str = payload.get("user_id")
    if not user_id:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    user.role_name = payload.get("role")
    user.token_permission = payload.get("permissions",[])
    return user


async def get_user_role(db: AsyncSession, user_id: str) -> Role | None:
    result = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_permissions(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .where(Permission.is_active.is_(True))
    )
    return [row[0] for row in result.all()]


def require_permission(permission_code: str):
    async def _checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        role = await get_user_role(db, current_user.id)
        if role and role.name.lower() == "super_admin":
            return current_user

        perms = await get_user_permissions(db, current_user.id)
        if permission_code not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )
        return current_user

    return _checker
