# app/services/warehouse_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.warehouse import WareHouseAddress
from app.schemas.warehouse import WarehouseCreate

async def create_warehouse(db: AsyncSession, data: WarehouseCreate, user_id: str):
    warehouse = WareHouseAddress(
        user_id=user_id,
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