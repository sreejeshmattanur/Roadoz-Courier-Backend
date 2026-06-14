from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.activity_log import ActivityLogListResponse
from app.services.activity_log_service import get_activity_logs
from app.dependencies.role_checker import get_current_user, require_permission, get_user_role
from app.models.user import User
from app.models.franchise import Franchise
from sqlalchemy import select

router = APIRouter(prefix="/activity-logs", tags=["Activity Logs"])

@router.get("", response_model=ActivityLogListResponse)
async def list_activity_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("activity_logs:view")),
):
    """
    List activity logs. 
    Super Admins see all logs.
    Franchise admins see logs for their employees.
    """
    role = await get_user_role(db, current_user.id)
    franchise_id = None
    
    if role and role.name.lower() == "franchise":
        result = await db.execute(select(Franchise.id).where(Franchise.user_id == current_user.id))
        franchise_id = result.scalar_one_or_none()
    elif role and role.name.lower() != "super_admin":
        franchise_id = current_user.franchise_id

    return await get_activity_logs(db, page=page, size=limit, franchise_id=franchise_id)
