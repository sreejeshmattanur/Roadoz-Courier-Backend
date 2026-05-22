import json
import math
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from fastapi import HTTPException, status
from app.models.user import User
from app.models.franchise import Franchise
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.franchise_code_counter import FranchiseCodeCounter
from app.schemas.franchise import FranchiseCreate, FranchiseUpdate, FranchiseResponse, FranchiseListResponse
from app.core.security import get_password_hash
from app.utils.redis import cache_set, cache_get, cache_delete
import uuid

from datetime import datetime, date, time
async def _generate_franchise_code(db: AsyncSession, location: str) -> str:
    year = datetime.utcnow().year
    loc_code = (location or "")[:3].upper().ljust(3, "X")

    result = await db.execute(
        select(FranchiseCodeCounter)
        .where(FranchiseCodeCounter.year == year)
        .with_for_update()
    )
    counter = result.scalar_one_or_none()

    if not counter:
        counter = FranchiseCodeCounter(year=year, last_sequence=1)
        db.add(counter)
        sequence = 1
    else:
        counter.last_sequence += 1
        sequence = counter.last_sequence

    await db.flush()

    return f"FR-{loc_code}-{year}-{str(sequence).zfill(4)}"


async def create_franchise(db: AsyncSession, data: FranchiseCreate) -> FranchiseResponse:
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == data.email_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    franchise_code = await _generate_franchise_code(db, data.proposed_location)

    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        name=data.full_name,
        email=data.email_id,
        password_hash=get_password_hash(data.password),
        phone=data.mobile_number,
        address=data.current_address,
    )
    db.add(user)
    await db.flush()

    role_result = await db.execute(select(Role).where(Role.name == "franchise"))
    franchise_role = role_result.scalar_one_or_none()
    if not franchise_role:
        franchise_role = Role(id=str(uuid.uuid4()), name="franchise")
        db.add(franchise_role)
        await db.flush()

    user_role_result = await db.execute(select(UserRole).where(UserRole.user_id == user.id))
    mapping = user_role_result.scalar_one_or_none()
    if not mapping:
        db.add(UserRole(user_id=user.id, role_id=franchise_role.id))
    else:
        mapping.role_id = franchise_role.id

    franchise = Franchise(
        id=str(uuid.uuid4()),
        user_id=user.id,
        franchise_code=franchise_code,
        name=data.full_name,
        email=data.email_id,
        phone=data.mobile_number,
        address=data.current_address,

        date_of_birth=data.date_of_birth,
        gender=data.gender,
        current_address=data.current_address,
        permanent_address=data.permanent_address,

        proposed_location=data.proposed_location,
        ownership_type=data.ownership_type,
        detailed_business_address=data.detailed_business_address,
        prior_experience=data.prior_experience,
        years_active=data.years_active,

        office_space_sqft=data.office_space_sqft,
        office_ownership=data.office_ownership,
        staff_count=data.staff_count,
        internet_availability=data.internet_availability,
        computer_laptop=data.computer_laptop,

        investment_capacity=data.investment_capacity,
        source_of_funds=data.source_of_funds,
        bank_name=data.bank_name,
        account_number=data.account_number,
        existing_loans=data.existing_loans,
        existing_loan_details=data.existing_loan_details,

        preferred_service_area=data.preferred_service_area,
        nearby_landmark=data.nearby_landmark,
        pincode=data.pincode,

        doc_id_proof=data.doc_id_proof,
        doc_address_proof=data.doc_address_proof,
        doc_photographs=data.doc_photographs,
        doc_business_registration=data.doc_business_registration,
        doc_bank_statement=data.doc_bank_statement,

        agree_to_terms=data.agree_to_terms,
        submission_place=data.submission_place,
        submission_date=data.submission_date,
    )
    db.add(franchise)
    await db.flush()

    await db.refresh(franchise)

    # Invalidate list cache
    await cache_delete("franchise_list")

    return FranchiseResponse.model_validate(franchise)















async def get_franchises(
    db: AsyncSession,
    page: int = 1,
    limit: int = 10,
    search: str = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> FranchiseListResponse:

    cache_key = (
        f"franchise_list:{page}:{limit}:{search or ''}:"
        f"{start_date or ''}:{end_date or ''}"
    )

    cached = await cache_get(cache_key)

    if cached:
        data = json.loads(cached)
        return FranchiseListResponse(**data)

    query = (
        select(Franchise)
        .order_by(
            Franchise.created_at.desc(),
            Franchise.id.desc()
        )
    )

    count_query = select(func.count()).select_from(Franchise)

    if search:

        filter_expr = or_(
            Franchise.name.ilike(f"%{search}%"),
            Franchise.email.ilike(f"%{search}%"),
            Franchise.phone.ilike(f"%{search}%"),
            Franchise.franchise_code.ilike(f"%{search}%"),
        )

        query = query.where(filter_expr)
        count_query = count_query.where(filter_expr)

    # START DATE FILTER
    if start_date:

        start_datetime = datetime.combine(
            start_date,
            time.min
        )

        query = query.where(
            Franchise.created_at >= start_datetime
        )

        count_query = count_query.where(
            Franchise.created_at >= start_datetime
        )

    # END DATE FILTER
    if end_date:

        end_datetime = datetime.combine(
            end_date,
            time.max
        )

        query = query.where(
            Franchise.created_at <= end_datetime
        )

        count_query = count_query.where(
            Franchise.created_at <= end_datetime
        )

    total = (
        await db.execute(count_query)
    ).scalar_one()

    offset = (page - 1) * limit

    result = await db.execute(
        query.offset(offset).limit(limit)
    )

    franchises = result.scalars().all()

    response = FranchiseListResponse(
        items=[
            FranchiseResponse.model_validate(f)
            for f in franchises
        ],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit)
        if total > 0 else 0,
    )

    await cache_set(
        cache_key,
        response.model_dump_json(),
        expire=120
    )

    return response


# async def get_franchises(
#     db: AsyncSession,
#     page: int = 1,
#     limit: int = 10,
#     search: str = None,
# ) -> FranchiseListResponse:
#     cache_key = f"franchise_list:{page}:{limit}:{search or ''}"
#     cached = await cache_get(cache_key)
#     if cached:
#         data = json.loads(cached)
#         return FranchiseListResponse(**data)

#     query = select(Franchise).order_by(Franchise.created_at.desc(), Franchise.id.desc())
#     count_query = select(func.count()).select_from(Franchise)

#     if search:
#         filter_expr = or_(
#             Franchise.name.ilike(f"%{search}%"),
#             Franchise.email.ilike(f"%{search}%"),
#             Franchise.phone.ilike(f"%{search}%"),
#             Franchise.franchise_code.ilike(f"%{search}%"),
#         )
#         query = query.where(filter_expr)
#         count_query = count_query.where(filter_expr)

#     total = (await db.execute(count_query)).scalar_one()
#     offset = (page - 1) * limit
#     result = await db.execute(query.offset(offset).limit(limit))
#     franchises = result.scalars().all()

#     response = FranchiseListResponse(
#         items=[FranchiseResponse.model_validate(f) for f in franchises],
#         total=total,
#         page=page,
#         limit=limit,
#         pages=math.ceil(total / limit) if total > 0 else 0,
#     )

#     await cache_set(cache_key, response.model_dump_json(), expire=120)
#     return response














async def get_franchise_by_id(db: AsyncSession, franchise_id: str) -> FranchiseResponse:
    cache_key = f"franchise:{franchise_id}"
    cached = await cache_get(cache_key)
    if cached:
        return FranchiseResponse(**json.loads(cached))

    result = await db.execute(select(Franchise).where(Franchise.id == franchise_id))
    franchise = result.scalar_one_or_none()
    if not franchise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    resp = FranchiseResponse.model_validate(franchise)
    await cache_set(cache_key, resp.model_dump_json(), expire=300)
    return resp


async def update_franchise(db: AsyncSession, franchise_id: str, data: FranchiseUpdate) -> FranchiseResponse:
    result = await db.execute(select(Franchise).where(Franchise.id == franchise_id))
    franchise = result.scalar_one_or_none()
    if not franchise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    update_data = data.model_dump(exclude_unset=True)

    if "email_id" in update_data and update_data["email_id"] != franchise.email:
        result = await db.execute(select(User).where(User.email == update_data["email_id"]))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    update_data.pop("franchise_code", None)

    if "full_name" in update_data:
        franchise.name = update_data["full_name"]
    if "email_id" in update_data:
        franchise.email = update_data["email_id"]
    if "mobile_number" in update_data:
        franchise.phone = update_data["mobile_number"]
    if "current_address" in update_data:
        franchise.current_address = update_data["current_address"]
        franchise.address = update_data["current_address"]

    for field, value in update_data.items():
        if field in {"full_name", "email_id", "mobile_number", "current_address"}:
            continue
        setattr(franchise, field, value)

    # Also update User record
    result = await db.execute(select(User).where(User.id == franchise.user_id))
    user = result.scalar_one_or_none()
    if user:
        if "full_name" in update_data:
            user.name = update_data["full_name"]
        if "mobile_number" in update_data:
            user.phone = update_data["mobile_number"]
        if "email_id" in update_data:
            user.email = update_data["email_id"]
        if "current_address" in update_data:
            user.address = update_data["current_address"]

    await db.flush()

    await db.refresh(franchise)

    await cache_delete(f"franchise:{franchise_id}")
    await cache_delete("franchise_list")

    return FranchiseResponse.model_validate(franchise)


async def delete_franchise(db: AsyncSession, franchise_id: str) -> dict:
    result = await db.execute(select(Franchise).where(Franchise.id == franchise_id))
    franchise = result.scalar_one_or_none()
    if not franchise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Franchise not found")

    # Delete user (cascade deletes franchise)
    result = await db.execute(select(User).where(User.id == franchise.user_id))
    user = result.scalar_one_or_none()
    if user:
        await db.delete(user)

    await db.flush()
    await cache_delete(f"franchise:{franchise_id}")
    await cache_delete("franchise_list")

    return {"message": "Franchise deleted successfully"}
