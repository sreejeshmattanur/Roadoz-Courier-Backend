# app/api/routes/warehouse.py

from fastapi import APIRouter, Depends,HTTPException,status,Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from sqlalchemy import select, and_, or_, func
from app.schemas.warehouse import WarehouseCreate, WarehouseResponse,WarehouseAddressUpdate,WarehouseAddressResponse
from app.services.warehouse_service import create_warehouse, get_all_warehouses
from app.models.user import User
from app.dependencies.role_checker import get_current_user
from app.models.warehouse import WareHouseAddress
from sqlalchemy import select,and_
from datetime import datetime,time
from typing import Optional
from datetime import date
from app.dependencies.role_checker import get_current_user, require_permission
router = APIRouter(prefix="/warehouse", tags=["Warehouse"])

@router.post("/warehousecreate/", response_model=WarehouseResponse)
async def create_warehouse_route(
    data: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("warehouse:create"))  
):
    try:
        return await create_warehouse(db, data, current_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f"Error creating warehouse: {str(e)}")



@router.get("/getall/")
async def list_warehouses(
    search: Optional[str] = Query(
        None,
        description="Search by nickname / contact name / phone / pincode"
    ),

    start_date: Optional[date] = Query(
        None,
        description="Start date"
    ),

    end_date: Optional[date] = Query(
        None,
        description="End date"
    ),

    page: int = Query(1, ge=1),

    limit: int = Query(10, ge=1, le=100),

    db: AsyncSession = Depends(get_db),

    current_user: User = Depends(get_current_user)
):

    offset = (page - 1) * limit

    filters = []

    if search:

        filters.append(
            or_(
                WareHouseAddress.nickname.ilike(f"%{search}%"),
                WareHouseAddress.contact_name.ilike(f"%{search}%"),
                WareHouseAddress.phone.ilike(f"%{search}%"),
                WareHouseAddress.pincode.ilike(f"%{search}%"),
                WareHouseAddress.city.ilike(f"%{search}%"),
                WareHouseAddress.state.ilike(f"%{search}%"),
            )
        )

    if start_date:

        filters.append(
            func.date(WareHouseAddress.created_at) >= start_date
        )

    if end_date:

        filters.append(
            func.date(WareHouseAddress.created_at) <= end_date
        )

    franchise_id = current_user.franchise_id
    is_global = False
    
    if not franchise_id:
        from app.models.franchise import Franchise
        franchise = (await db.execute(select(Franchise).where(Franchise.user_id == current_user.id))).scalar_one_or_none()
        if franchise:
            franchise_id = franchise.id
        else:
            is_global = True

    if not is_global:
        if franchise_id:
            filters.append(WareHouseAddress.franchise_id == franchise_id)
        else:
            filters.append(WareHouseAddress.user_id == str(current_user.id))

    stmt = (
        select(WareHouseAddress)
        .where(and_(*filters))
        .order_by(WareHouseAddress.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)

    warehouses = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(WareHouseAddress)
        .where(and_(*filters))
    )

    total_result = await db.execute(count_stmt)

    total = total_result.scalar() or 0

    total_pages = (total + limit - 1) // limit

    return {
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },

        "filters": {
            "search": search,
            "start_date": start_date,
            "end_date": end_date,
        },

        "data": [
            {
                "id": warehouse.id,
                "user_id": warehouse.user_id,
                "franchise_id": warehouse.franchise_id,
                "nickname": warehouse.nickname,
                "contact_name": warehouse.contact_name,
                "phone": warehouse.phone,
                "email": warehouse.email,
                "address_line_1": warehouse.address_line_1,
                "address_line_2": warehouse.address_line_2,
                "pincode": warehouse.pincode,
                "city": warehouse.city,
                "state": warehouse.state,
                "country": warehouse.country,
                "created_at": warehouse.created_at,
                "updated_at": warehouse.updated_at,
            }

            for warehouse in warehouses
        ]
    }







@router.get("/getonebyonewithid/{address_id}", response_model=WarehouseAddressResponse)
async def get_address_by_id(address_id: str,db: AsyncSession = Depends(get_db),current_user: User = Depends(get_current_user)):
    result = await db.execute(select(WareHouseAddress).where(WareHouseAddress.id == address_id))
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    return address




@router.get("/getonebyonewithpincode/{pincode}",response_model=list[WarehouseAddressResponse])
async def get_address_by_id(
    pincode: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    result = await db.execute(select(WareHouseAddress).where(WareHouseAddress.pincode == pincode))
    addresses = result.scalars().all()
    if not addresses:
        raise HTTPException(status_code=404,detail="Address not found")
    return addresses





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






@router.delete("/delete-warehouse-address/{warehouse_address_id}")
async def delete_warehouse_address(
    warehouse_address_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WareHouseAddress).where(WareHouseAddress.id == warehouse_address_id))
    warehouse_address = result.scalar_one_or_none()
    if not warehouse_address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Warehouse address not found")
    await db.delete(warehouse_address)
    await db.commit()
    return {"success": True,"message": "Warehouse address deleted successfully"}
    
    
    

@router.get("/warehouse-addresses")
async def get_warehouse_addresses(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    franchise_id = current_user.franchise_id
    is_global = False
    
    if not franchise_id:
        from app.models.franchise import Franchise
        franchise = (await db.execute(select(Franchise).where(Franchise.user_id == current_user.id))).scalar_one_or_none()
        if franchise:
            franchise_id = franchise.id
        else:
            is_global = True

    query = select(WareHouseAddress)
    filters = []

    if not is_global:
        if franchise_id:
            filters.append(WareHouseAddress.franchise_id == franchise_id)
        else:
            filters.append(WareHouseAddress.user_id == str(current_user.id))

    if name:
        filters.append(
            (
                WareHouseAddress.contact_name.ilike(f"%{name}%")
            ) |
            (
                WareHouseAddress.nickname.ilike(f"%{name}%")))
    if start_date:
        start_datetime = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(),time.min)
        filters.append(WareHouseAddress.created_at >= start_datetime)
    if end_date:
        end_datetime = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date(),time.max)
        filters.append(WareHouseAddress.created_at <= end_datetime)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(WareHouseAddress.created_at.desc())
    result = await db.execute(query)
    warehouse_addresses = result.scalars().all()
    return {
        "success": True,
        "count": len(warehouse_addresses),
        "data": [
            {
                "id": warehouse.id,
                "nickname": warehouse.nickname,
                "contact_name": warehouse.contact_name,
                "phone": warehouse.phone,
                "email": warehouse.email,
                "address_line_1": warehouse.address_line_1,
                "address_line_2": warehouse.address_line_2,
                "pincode": warehouse.pincode,
                "city": warehouse.city,
                "state": warehouse.state,
                "country": warehouse.country,
                "created_at": warehouse.created_at,
            }
            for warehouse in warehouse_addresses
        ]
    }    