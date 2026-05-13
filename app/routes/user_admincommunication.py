from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_
from app.core.database import get_db
from app.models.user_admincommunication import (AdminandUserMessage)
from app.utils.websocket_auth import (get_current_websocket_user)
router = APIRouter(prefix="/chat",tags=["Chat"])


@router.get("/messages")
async def get_messages(receiver_id: str,receiver_type: str,current_user = Depends(get_current_websocket_user),db: AsyncSession = Depends(get_db)):
    user_id = current_user["user_id"]
    user_type = current_user["user_type"]
    result = await db.execute(
        select(AdminandUserMessage).where(or_(
                and_(
                    AdminandUserMessage.sender_id == user_id,
                    AdminandUserMessage.sender_type == user_type,
                    AdminandUserMessage.receiver_id == receiver_id,
                    AdminandUserMessage.receiver_type == receiver_type),
                and_(
                    AdminandUserMessage.sender_id == receiver_id,
                    AdminandUserMessage.sender_type == receiver_type,
                    AdminandUserMessage.receiver_id == user_id,
                    AdminandUserMessage.receiver_type == user_type
                ))
        ).order_by(
            AdminandUserMessage.created_at.asc()
        )
    )

    messages = result.scalars().all()

    return {
        "success": True,
        "messages": messages}