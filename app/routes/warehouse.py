# app/api/routes/warehouse.py

from fastapi import APIRouter, Depends,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.warehouse import WarehouseCreate, WarehouseResponse,WarehouseAddressUpdate,WarehouseAddressResponse
from app.services.warehouse_service import create_warehouse, get_all_warehouses
from app.models.user import User
from app.dependencies.role_checker import get_current_user
from app.models.warehouse import WareHouseAddress
from sqlalchemy import select
from datetime import datetime

router = APIRouter(prefix="/warehouse", tags=["Warehouse"])


@router.post("/warehousecreate/", response_model=WarehouseResponse,)
async def create_warehouse_route(
    data: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await create_warehouse(db, data, current_user.id)


@router.get("/getall/", response_model=list[WarehouseResponse])
async def list_warehouses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await get_all_warehouses(db)




@router.get("/getonebyone/{address_id}", response_model=WarehouseAddressResponse)
async def get_address_by_id(address_id: str,db: AsyncSession = Depends(get_db),current_user: User = Depends(get_current_user)):
    result = await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == address_id))
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    return address



@router.patch("/update/{address_id}", response_model=WarehouseAddressResponse)
async def update_address(address_id: str,data: WarehouseAddressUpdate,db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == address_id))
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(address, key, value)
    address.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(address)

    return address