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
    """
    Unified chat WebSocket endpoint for admin/staff ↔ customer communication.

    **URL:** ``ws://127.0.0.1:8000/api/v1/ws/admin/chat?token=<JWT>``

    **Who can connect:**
    - **AuthUser** (customers / end-users): always allowed to connect and receive messages.
      They may also *send* messages (their messages are stored and forwarded to the recipient).
    - **User** (admin / staff): must have the ``communication:send`` RBAC permission
      (or be ``super_admin``). Connection is rejected with code ``4003`` if permission is absent.

    **Admin assigns permission via:** ``POST /api/v1/rbac/assign-role`` then
    ensure the assigned role has ``communication:send`` in its permissions
    (``POST /api/v1/rbac/permissions`` + ``PUT /api/v1/rbac/roles/{role_id}``).

    **Message format (send):**
    ```json
    {
        "receiver_id":   "<target user/auth_user UUID>",
        "receiver_type": "user | auth_user",
        "message":       "Hello!"
    }
    ```

    **Message format (receive):**
    ```json
    {
        "sender_id":     "<UUID>",
        "sender_type":   "user | auth_user",
        "receiver_id":   "<UUID>",
        "receiver_type": "user | auth_user",
        "message":       "Hello!"
    }
    ```
    """
    # ── 1. Authenticate ───────────────────────────────────────────────────────
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    db: AsyncSession = AsyncSessionLocal()
    try:
        try:
            user_data = await verify_websocket_token(token, db=db)
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

        user_id: str = user_data["user_id"]
        user_type: str = user_data["user_type"]

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

        # ── 4. Message loop ───────────────────────────────────────────────────
        while True:
            data = await websocket.receive_json()

            receiver_id: str | None = data.get("receiver_id")
            receiver_type: str | None = data.get("receiver_type")
            message: str | None = data.get("message")

            if not receiver_id or not receiver_type or not message:
                await websocket.send_json({
                    "event": "error",
                    "detail": "Payload must contain receiver_id, receiver_type, and message",
                })
                continue

            # Re-check permission on each send for User/staff
            # (catches mid-session revocations)
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
            }

            # Forward to recipient (if online)
            await manager.send_message(receiver_type, receiver_id, payload)

            # Echo back to sender for confirmation
            await websocket.send_json({**payload, "event": "sent"})

    except WebSocketDisconnect:
        manager.disconnect(user_type, user_id)
    except Exception:
        try:
            manager.disconnect(user_type, user_id)
        except Exception:
            pass
    finally:
        await db.close()