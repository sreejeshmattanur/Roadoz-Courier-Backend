from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.models.user_admincommunication import AdminandUserMessage
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.permission import Permission

from app.websocket.user_admin_manager import manager
from app.utils.websocket_auth import verify_websocket_token

router = APIRouter(prefix="/ws/admin", tags=["WebSocket"])

CHAT_PERMISSION = "communication:send"


async def _has_chat_permission(db: AsyncSession, user_id: str) -> bool:
    """
    Return True if the User (admin/staff) has the 'communication:send' permission
    via their RBAC role, OR if they have the super_admin role.
    """
    # Check if super_admin role
    role_result = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    role = role_result.scalar_one_or_none()
    if role and role.name.lower() == "super_admin":
        return True

    # Check explicit permission
    perm_result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .where(Permission.code == CHAT_PERMISSION)
        .where(Permission.is_active.is_(True))
    )
    return perm_result.scalar_one_or_none() is not None


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    # ── 1. Authenticate ───────────────────────────────────────────────────────
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    db: AsyncSession = AsyncSessionLocal()
    user_id = None
    user_type = None
    try:
        try:
            user_data = await verify_websocket_token(token, db=db)
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

        user_id = user_data["user_id"]
        user_type = user_data["user_type"]

        # ── 2. Authorise (only User/staff need explicit permission) ───────────
        if user_type != "auth_user":
            # Admin / staff path — check RBAC
            allowed = await _has_chat_permission(db, user_id)
            if not allowed:
                await websocket.close(
                    code=4003,
                    reason="Permission denied: you need the 'communication:send' permission",
                )
                return

        # ── 3. Accept connection ──────────────────────────────────────────────
        await manager.connect(user_type, user_id, websocket)

        # Send a welcome confirmation
        await websocket.send_json({
            "event": "connected",
            "user_id": user_id,
            "user_type": user_type,
            "message": "Connected to chat. You can now send and receive messages.",
        })
        
        # Broadcast online status to opposite type
        opposite_type = "user" if user_type == "auth_user" else "auth_user"
        await manager.broadcast_to_type(opposite_type, {
            "event": "user_status",
            "user_id": user_id,
            "user_type": user_type,
            "status": "online"
        })

        # ── 4. Message loop ───────────────────────────────────────────────────
        while True:
            data = await websocket.receive_json()

            event = data.get("event", "message")
            
            if event == "check_status":
                target_id = data.get("target_id")
                target_type = data.get("target_type")
                if target_id and target_type:
                    is_online = manager.is_online(target_type, target_id)
                    await websocket.send_json({
                        "event": "user_status",
                        "user_id": target_id,
                        "user_type": target_type,
                        "status": "online" if is_online else "offline"
                    })
                continue

            receiver_id = data.get("receiver_id")
            receiver_type = data.get("receiver_type")
            message = data.get("message")

            if not receiver_id or not receiver_type or not message:
                await websocket.send_json({
                    "event": "error",
                    "detail": "Payload must contain receiver_id, receiver_type, and message",
                })
                continue

            # Re-check permission on each send for User/staff
            if user_type != "auth_user":
                still_allowed = await _has_chat_permission(db, user_id)
                if not still_allowed:
                    await websocket.send_json({
                        "event": "error",
                        "detail": "Permission revoked. You can no longer send messages.",
                    })
                    break

            # Persist message
            new_message = AdminandUserMessage(
                sender_id=user_id,
                sender_type=user_type,
                receiver_id=receiver_id,
                receiver_type=receiver_type,
                message=message,
            )
            db.add(new_message)
            await db.commit()

            payload = {
                "event": "message",
                "sender_id": user_id,
                "sender_type": user_type,
                "receiver_id": receiver_id,
                "receiver_type": receiver_type,
                "message": message,
                "sender_online": True,
                "receiver_online": manager.is_online(receiver_type, receiver_id)
            }

            # Forward to recipient (if online)
            await manager.send_message(receiver_type, receiver_id, payload)

            # Echo back to sender for confirmation
            await websocket.send_json({**payload, "event": "sent"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if user_type and user_id:
            try:
                manager.disconnect(user_type, user_id, websocket)
                # If they have no other tabs open, broadcast offline
                if not manager.is_online(user_type, user_id):
                    opposite_type = "user" if user_type == "auth_user" else "auth_user"
                    await manager.broadcast_to_type(opposite_type, {
                        "event": "user_status",
                        "user_id": user_id,
                        "user_type": user_type,
                        "status": "offline"
                    })
            except Exception:
                pass
        await db.close()