from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from sqlalchemy import select
from app.models.order import Order
from app.models.consigeeauth import AuthUser
from app.models.consignee import Consignee

from app.models.consigeereview import (ProductReview,ReviewStatus)
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.coningeereview import (ProductReviewCreate,ProductReviewApprove,ProductReviewResponse,ApprovedReviewPaginationResponse,ProductReviewPaginationResponse)
from app.dependencies.consigeeuser import get_current_user as get_current_consigee
from app.dependencies.role_checker import get_current_user as get_current_adminuser
from math import ceil
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func

router = APIRouter(prefix="/product-reviews",tags=["Order Reviews"])

@router.post("/create/", response_model=ProductReviewResponse)
async def create_product_review(
    payload: ProductReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_consigee)):
    order_result = await db.execute(
        select(Order).where(Order.id == payload.order_id))
    order = order_result.scalars().first()
    if not order:
        raise HTTPException(status_code=404,detail="Order not found")
    consignee_result = await db.execute(
        select(AuthUser).where(AuthUser.id == current_user.id))
    consignee = consignee_result.scalars().first()
    if not consignee:
        raise HTTPException(status_code=404,detail="Consignee not found")
    if order.status != "Delivered":
        raise HTTPException(status_code=400,detail="Review allowed only after delivery")
    review = ProductReview(
        order_id=payload.order_id,
        auth_users_id=current_user.id,
        review=payload.review,
        rating=payload.rating,
        status=ReviewStatus.PENDING)
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review






@router.put("/approve/{review_id}")
async def approve_product_review(
    review_id: str,
    approveor:bool,
    admin_comment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_adminuser)):
    review_result = await db.execute(
        select(ProductReview).where(ProductReview.id == review_id))
    review = review_result.scalars().first()
    if not review:
        raise HTTPException(status_code=404,detail="Review not found")
    review.admin_approved = approveor
    review.admin_comment = admin_comment
    if approveor:
      review.status = ReviewStatus.APPROVED
    else:
        review.status = ReviewStatus.REJECTED
    await db.commit()
    await db.refresh(review)
    return {
        "message": "Review approved successfully",
        "data": {
            "id": review.id,
            "order_id": review.order_id,
            "review": review.review,
            "rating": review.rating,
            "status": review.status,
            "admin_approved": review.admin_approved,
            "admin_comment": review.admin_comment,
            "updated_at": review.updated_at
        }
    }
   
          
    
@router.get("/all-reviews/",response_model=ProductReviewPaginationResponse)
async def get_all_reviews(page: int = Query(1, ge=1),limit: int = Query(5, ge=1),db: AsyncSession = Depends(get_db)):
    total_result = await db.execute(select(func.count(ProductReview.id)))
    total_reviews = total_result.scalar()
    skip = (page - 1) * limit
    result = await db.execute(
        select(ProductReview)
        .order_by(ProductReview.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    reviews = result.scalars().all()
    return {
        "total_reviews": total_reviews,
        "total_pages": ceil(total_reviews / limit),
        "current_page": page,
        "limit": limit,
        "data": reviews
    }
    
    
    
@router.get("/approved-reviews/",response_model=ApprovedReviewPaginationResponse)
async def get_approved_reviews(page: int = Query(1, ge=1),limit: int = Query(5, ge=1),db: AsyncSession = Depends(get_db)):
    total_result = await db.execute(select(func.count(ProductReview.id)).where(ProductReview.admin_approved == True))
    total_reviews = total_result.scalar()
    skip = (page - 1) * limit
    result = await db.execute(
        select(ProductReview)
        .where(ProductReview.admin_approved == True)
        .order_by(ProductReview.created_at.desc())
        .offset(skip).limit(limit))

    reviews = result.scalars().all()

    return {
        "total_reviews": total_reviews,
        "total_pages": ceil(total_reviews / limit),
        "current_page": page,
        "limit": limit,
        "data": reviews
    }        