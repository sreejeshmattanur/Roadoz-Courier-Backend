from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.schemas.franchise import FranchiseCreate, FranchiseUpdate, FranchiseResponse, FranchiseListResponse
from app.services.franchise_service import (
    create_franchise,
    get_franchises,
    get_franchise_by_id,
    update_franchise,
    delete_franchise,
)
from datetime import datetime, date, time
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User

router = APIRouter(prefix="/franchise", tags=["Franchise"])


@router.post("", response_model=FranchiseResponse, status_code=201)
async def create(
    data: FranchiseCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("franchises:create")),
):
    """Create a new franchise. **Super Admin only.**"""
    return await create_franchise(db, data)


# @router.get("", response_model=FranchiseListResponse)
# async def list_franchises(
#     page: int = Query(1, ge=1, description="Page number"),
#     limit: int = Query(10, ge=1, le=100, description="Items per page"),
#     search: Optional[str] = Query(None, description="Search by name, email, phone, or code"),
#     db: AsyncSession = Depends(get_db),
#     _: User = Depends(get_current_user),
#     __: User = Depends(require_permission("franchises:view")),
# ):
#     """
#     List all franchises with pagination and search.

#     - Search works across: name, email, phone, franchise_code
#     - Example: `/api/v1/franchise?search=kochi&page=1&limit=10`
#     """
#     return await get_franchises(db, page=page, limit=limit, search=search)


@router.get(
    "",
    response_model=FranchiseListResponse
)
async def list_franchises(

    page: int = Query(
        1,
        ge=1,
        description="Page number"
    ),

    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Items per page"
    ),

    start_date: Optional[date] = Query(
        None,
        description="Start date"
    ),

    end_date: Optional[date] = Query(
        None,
        description="End date"
    ),

    search: Optional[str] = Query(
        None,
        description="Search by name, email, phone, or code"
    ),

    db: AsyncSession = Depends(get_db),

    _: User = Depends(get_current_user),

    __: User = Depends(
        require_permission("franchises:view")
    ),
):
    """
    List all franchises with pagination and search.

    - Search works across: name, email, phone, franchise_code
    - Example:
      `/api/v1/franchise?search=kochi&page=1&limit=10`
    """

    return await get_franchises(
        db=db,
        page=page,
        limit=limit,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )









@router.get("/{franchise_id}", response_model=FranchiseResponse)
async def get_by_id(
    franchise_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("franchises:view")),
):
    """Get a specific franchise by ID."""
    return await get_franchise_by_id(db, franchise_id)


@router.put("/{franchise_id}", response_model=FranchiseResponse)
async def update(
    franchise_id: str,
    data: FranchiseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("franchises:edit")),
):
    """Update a franchise. **Super Admin only.**"""
    return await update_franchise(db, franchise_id, data)


@router.delete("/{franchise_id}")
async def delete(
    franchise_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission("franchises:delete")),
):
    """Delete a franchise. **Super Admin only.**"""
    return await delete_franchise(db, franchise_id)
