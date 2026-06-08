from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.core.database  import get_db
from app.models.projectreview import ProjectReview
from app.models.user import User
from app.schemas.projectreview import (
    CreateReviewSchema,
    UpdateReviewSchema,
    ReviewResponseSchema
)
from app.dependencies.role_checker import get_current_user, require_permission


router = APIRouter(prefix="/project/reviews", tags=["Service Reviews"])


# =====================================================
# CREATE REVIEW
# =====================================================


@router.post("/create", response_model=ReviewResponseSchema)
async def create_review(
    payload: CreateReviewSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:create"))):
    new_review = ProjectReview(user_id=current_user.id,rating=payload.rating,review=payload.review)
    db.add(new_review)
    await db.commit()
    await db.refresh(new_review)
    return new_review


# =====================================================
# SHOW ALL REVIEWS WITH PAGINATION
# =====================================================

@router.get("/all")
async def get_all_reviews(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("reviews:view"))):
    skip = (page - 1) * limit
    total_query = await db.execute(select(func.count()).select_from(ProjectReview))
    total_reviews = total_query.scalar()
    query = await db.execute(select(ProjectReview).offset(skip).limit(limit).order_by(ProjectReview.created_at.desc()))
    reviews = query.scalars().all()
    return {
        "success": True,
        "page": page,
        "limit": limit,"total_reviews": total_reviews,"data": reviews}


# =====================================================
# GET CURRENT USER REVIEWS
# =====================================================

@router.get("/my")
async def get_my_reviews(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:view"))):
    query = await db.execute(
        select(ProjectReview).where(ProjectReview.user_id == current_user.id))
    reviews = query.scalars().all()
    return {
        "success": True,
        "count": len(reviews),"data": reviews}


# =====================================================
# UPDATE REVIEW (ADMIN ONLY)
# =====================================================

@router.put("/update/{review_id}", response_model=ReviewResponseSchema)
async def update_review(
    review_id: str,
    payload: UpdateReviewSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:edit"))):
    
    from app.dependencies.role_checker import is_global_user
    if not await is_global_user(db, current_user):
        raise HTTPException(status_code=403, detail="Only global admins can update reviews")
    query = await db.execute(select(ProjectReview).where(ProjectReview.id == review_id))

    review = query.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404,detail="Review not found")
    if payload.rating is not None:
        review.rating = payload.rating
    if payload.review is not None:
        review.review = payload.review
    review.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(review)

    return review