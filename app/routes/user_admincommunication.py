from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, desc
from typing import Optional

from app.core.database import get_db
from app.models.user_admincommunication import AdminandUserMessage
from app.models.consigeeauth import AuthUser
from app.utils.jwt import verify_access_token

# Admin dependencies
from app.dependencies.role_checker import get_current_user as get_admin_user, require_permission
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
from app.models.permission import Permission

# Customer dependencies
from app.dependencies.consigeeuser import get_current_user as get_customer_user

router = APIRouter(prefix="/chatwithadminanduser", tags=["ChatSection"])

async def get_current_user_from_token(token: str = Depends(verify_access_token)):
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token

@router.get("/messages")
async def get_messages(
    receiver_id: str,
    receiver_type: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("communication:view"))
):
    """
    Get messages between the current admin/user and a specific user/auth_user.
    """
    user_id = current_user.id
    user_type = "user" # Since this endpoint uses get_current_user, it's always an admin/staff User

    result = await db.execute(
        select(AdminandUserMessage).where(
            or_(
                and_(
                    AdminandUserMessage.sender_id == user_id,
                    AdminandUserMessage.sender_type == user_type,
                    AdminandUserMessage.receiver_id == receiver_id,
                    AdminandUserMessage.receiver_type == receiver_type
                ),
                and_(
                    AdminandUserMessage.sender_id == receiver_id,
                    AdminandUserMessage.sender_type == receiver_type,
                    AdminandUserMessage.receiver_id == user_id,
                    AdminandUserMessage.receiver_type == user_type
                )
            )
        ).order_by(AdminandUserMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return {"success": True, "messages": messages}

@router.get("/conversations")
async def get_conversations(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("communication:view"))
):
    """
    Get a list of all distinct users (AuthUsers) the current admin has chatted with,
    including the last message.
    """
    user_id = current_user.id
    user_type = "user"

    # We need to find all unique conversations for this user
    # A simple approach is to get all messages where sender or receiver is this user,
    # order by created_at desc, and then manually group by the 'other' user.
    result = await db.execute(
        select(AdminandUserMessage).where(
            or_(
                and_(AdminandUserMessage.sender_id == user_id, AdminandUserMessage.sender_type == user_type),
                and_(AdminandUserMessage.receiver_id == user_id, AdminandUserMessage.receiver_type == user_type)
            )
        ).order_by(desc(AdminandUserMessage.created_at))
    )
    messages = result.scalars().all()

    conversations = {}
    for msg in messages:
        # Determine who the 'other' person is
        if msg.sender_id == user_id and msg.sender_type == user_type:
            other_id = msg.receiver_id
            other_type = msg.receiver_type
        else:
            other_id = msg.sender_id
            other_type = msg.sender_type
            
        key = f"{other_type}_{other_id}"
        if key not in conversations:
            conversations[key] = {
                "user_id": other_id,
                "user_type": other_type,
                "last_message": msg.message,
                "last_message_at": msg.created_at,
                "unread_count": 0 # You'd need an 'is_read' field to implement this properly
            }
            
    # Now we want to enrich the AuthUser information (name, email, etc.)
    # Collect all auth_user ids
    auth_user_ids = [c["user_id"] for c in conversations.values() if c["user_type"] == "auth_user"]
    
    if auth_user_ids:
        auth_users_result = await db.execute(
            select(AuthUser).where(AuthUser.id.in_(auth_user_ids))
        )
        auth_users = {u.id: u for u in auth_users_result.scalars().all()}
        
        for key, conv in conversations.items():
            if conv["user_type"] == "auth_user" and conv["user_id"] in auth_users:
                user_obj = auth_users[conv["user_id"]]
                conv["user_name"] = user_obj.name
                conv["user_email"] = user_obj.email
                conv["user_phone"] = user_obj.phone
    
    return {"success": True, "conversations": list(conversations.values())}

@router.get("/auth-users")
async def get_chatable_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("communication:send"))
):
    """
    Get a list of AuthUsers (customers) that admins can start a chat with.
    Only admins with communication:send permission can access this.
    """
    query = select(AuthUser)
    
    if search:
        query = query.where(
            or_(
                AuthUser.name.ilike(f"%{search}%"),
                AuthUser.email.ilike(f"%{search}%"),
                AuthUser.phone.ilike(f"%{search}%")
            )
        )
        
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {
        "success": True,
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "user_type": "auth_user"
            } for u in users
        ]
    }

# ==========================================
# CUSTOMER (AUTH_USER) ENDPOINTS
# ==========================================

@router.get("/customer/messages")
async def get_customer_messages(
    receiver_id: str,
    current_customer: AuthUser = Depends(get_customer_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get messages for the currently logged in customer (AuthUser).
    Customers can only see their own chat history.
    """
    user_id = current_customer.id
    user_type = "auth_user"
    receiver_type = "user" # Customers usually message admins/staff

    result = await db.execute(
        select(AdminandUserMessage).where(
            or_(
                and_(
                    AdminandUserMessage.sender_id == user_id,
                    AdminandUserMessage.sender_type == user_type,
                    AdminandUserMessage.receiver_id == receiver_id,
                    AdminandUserMessage.receiver_type == receiver_type
                ),
                and_(
                    AdminandUserMessage.sender_id == receiver_id,
                    AdminandUserMessage.sender_type == receiver_type,
                    AdminandUserMessage.receiver_id == user_id,
                    AdminandUserMessage.receiver_type == user_type
                )
            )
        ).order_by(AdminandUserMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return {"success": True, "messages": messages}

@router.get("/customer/support-agents")
async def get_support_agents(
    current_customer: AuthUser = Depends(get_customer_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a list of support agents (Admins/Staff) that the customer can start a chat with.
    This returns users from the User table who have the 'communication:send' permission
    or the 'super_admin' role.
    """
    # Query users who have the required permission or role
    query = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(
            User.is_active.is_(True),
            or_(
                Role.name == "super_admin",
                and_(
                    Permission.code == "communication:send",
                    Permission.is_active.is_(True)
                )
            )
        )
        .distinct()
    )
    
    result = await db.execute(query)
    agents = result.scalars().all()
    
    return {
        "success": True,
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "email": agent.email,
                "user_type": "user"
            } for agent in agents
        ]
    }