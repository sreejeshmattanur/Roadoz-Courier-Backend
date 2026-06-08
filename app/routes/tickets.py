from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.schemas.tickets import TicketCreate, TicketOut, TicketListResponse
from app.dependencies.role_checker import get_current_user, require_permission
from app.services.ticket_service import create_ticket,list_tickets
from app.models.user import User





router = APIRouter(prefix="/tickets", tags=["Tickets"])




@router.post("/", response_model=TicketOut)
async def create_ticket_api(
    data: TicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("tickets:create")),
):
    try:
        return await create_ticket(db, data, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.get("/", response_model=TicketListResponse)
async def get_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("tickets:view")),
):
    return await list_tickets(
        db=db,
        page=page,
        limit=limit,
        status=status,
        priority=priority,
    )