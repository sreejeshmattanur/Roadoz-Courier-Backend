# app/api/routes/warehouse.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.warehouse import WarehouseCreate, WarehouseResponse
from app.services.warehouse_service import create_warehouse, get_all_warehouses
from app.models.user import User
from app.dependencies.role_checker import get_current_user

router = APIRouter(prefix="/warehouse", tags=["Warehouse"])


@router.post("/warehouse/", response_model=WarehouseResponse)
async def create_warehouse_route(
    data: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await create_warehouse(db, data, current_user.id)


@router.get("/", response_model=list[WarehouseResponse])
async def list_warehouses(
    db: AsyncSession = Depends(get_db),
):
    return await get_all_warehouses(db)