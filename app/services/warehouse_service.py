# app/services/warehouse_service.py
from fastapi import  HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.warehouse import WareHouseAddress
from app.schemas.warehouse import WarehouseCreate
from app.services.order_service import _resolve_franchise_id
from app.models.user import User


async def create_warehouse(db: AsyncSession, data: WarehouseCreate, current_user: User):
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
    
    # Create new warehouse
    warehouse = WareHouseAddress(
        user_id=str(current_user.id),
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