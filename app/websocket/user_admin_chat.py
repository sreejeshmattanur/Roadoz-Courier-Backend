from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.user_admincommunication import AdminandUserMessage

from app.websocket.user_admin_manager import manager
from app.utils.websocket_auth import verify_websocket_token

router = APIRouter(prefix="/ws/admin",tags=["WebSocket"])
@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    user_data = await verify_websocket_token(token)
    user_id = user_data["user_id"]
    user_type = user_data["user_type"]
    await manager.connect(user_type,user_id,websocket)
    db: AsyncSession = AsyncSessionLocal()
    try:
        while True:
            data = await websocket.receive_json()
            receiver_id = data["receiver_id"]
            receiver_type = data["receiver_type"]
            message = data["message"]
            new_message = AdminandUserMessage(
                sender_id=user_id,
                sender_type=user_type,
                receiver_id=receiver_id,
                receiver_type=receiver_type,
                message=message
            )
            db.add(new_message)
            await db.commit()
            payload = {
                "sender_id": user_id,
                "sender_type": user_type,
                "receiver_id": receiver_id,
                "receiver_type": receiver_type,
                "message": message
            }
            await manager.send_message(
                receiver_type,
                receiver_id,
                payload
            )
    except WebSocketDisconnect:
        manager.disconnect(
            user_type,
            user_id
        )