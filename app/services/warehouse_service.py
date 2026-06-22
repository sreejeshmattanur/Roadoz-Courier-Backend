# app/services/warehouse_service.py
from fastapi import  HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.warehouse import WareHouseAddress
from app.schemas.warehouse import WarehouseCreate
from app.services.order_service import _resolve_franchise_id
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.core.security import get_password_hash


async def create_warehouse(db: AsyncSession, data: WarehouseCreate, current_user: User):
    # Check if email is already taken
    existing_user_result = await db.execute(
        select(User).where(User.email == data.email)
    )
    if existing_user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {data.email} is already in use."
        )

    # Check if warehouse already exists for this pincode
    existing = await db.execute(
        select(WareHouseAddress).where(WareHouseAddress.pincode == data.pincode)
    )
    existing_warehouse = existing.scalar_one_or_none()
    
    if existing_warehouse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Warehouse already exists for pincode {data.pincode}")
    franchise_id = await _resolve_franchise_id(db, current_user)
    
    # Create User account for the warehouse
    new_user = User(
        name=data.contact_name,
        email=data.email,
        password_hash=get_password_hash(data.password),
        phone=data.phone,
        pincode=data.pincode,
        address=data.address_line_1,
        is_active=True
    )
    db.add(new_user)
    await db.flush()

    # Assign the 'warehouse' role
    role_result = await db.execute(select(Role).where(Role.name == "warehouse"))
    warehouse_role = role_result.scalar_one_or_none()
    if not warehouse_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The 'warehouse' role does not exist in the database. Please run the seed script."
        )
    db.add(UserRole(user_id=new_user.id, role_id=warehouse_role.id))

    # Create new warehouse linked to the new user
    warehouse = WareHouseAddress(
        user_id=str(new_user.id),
        franchise_id=franchise_id,
        nickname=data.nickname,
        contact_name=data.contact_name,
        phone=data.phone,
        email=data.email,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        pincode=data.pincode,
        city=data.city,
        state=data.state,
        country=data.country,
    )
    
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    
    return warehouse


async def get_all_warehouses(db: AsyncSession):
    result = await db.execute(select(WareHouseAddress))
    return result.scalars().all()