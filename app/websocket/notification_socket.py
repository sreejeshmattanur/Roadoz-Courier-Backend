from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter(prefix="/websocket", tags=["WebSocket"])

@router.websocket("/ws/notifications")
async def notification_socket(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(
                f"Message received: {data}",
                websocket
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket)