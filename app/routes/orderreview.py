from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


from app.core.database  import get_db
from app.models.order import Order
from app.models.orderreview import OrderReview
from app.schemas.orderreview import (CreateReviewSchema,UpdateReviewSchema,ReviewResponseSchema)
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User


router = APIRouter(prefix="/reviews", tags=["Order Reviews"])


@router.post("/createreviews", response_model=ReviewResponseSchema)
async def create_review(
    payload: CreateReviewSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:create"))):
    order_query = await db.execute(select(Order).where(Order.id == payload.order_id))
    
    order = order_query.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404,detail="Order not found")
    new_review = OrderReview(order_id=payload.order_id,user_id=current_user.id,rating=payload.rating,review=payload.review)
    db.add(new_review)
    await db.commit()
    await db.refresh(new_review)
    return new_review




@router.get("/order/{order_id}")
async def get_all_reviews_of_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("reviews:view"))):

    query = await db.execute(select(OrderReview).where(OrderReview.order_id == order_id))
    reviews = query.scalars().all()

    return {"success": True,"count": len(reviews),"data": reviews}
    
    

@router.get("/my/reviews")
async def get_my_reviews(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:view"))):

    query = await db.execute(select(OrderReview).where(OrderReview.user_id == current_user.id))

    reviews = query.scalars().all()

    return {
        "success": True,
        "count": len(reviews),
        "data": reviews
    }
    
    



@router.patch("/review/update/{review_id}", response_model=ReviewResponseSchema)
async def update_review(
    review_id: str,
    payload: UpdateReviewSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:edit"))
):  
    from app.dependencies.role_checker import is_global_user
    if not await is_global_user(db, current_user):
        raise HTTPException(status_code=403, detail="Only global admins can update reviews")
    query = await db.execute(select(OrderReview).where(OrderReview.id == review_id))
    review = query.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(review, key, value)
    await db.commit()
    await db.refresh(review)
    return review





@router.delete("/{review_id}")
async def delete_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("reviews:delete"))):
    query = await db.execute(select(OrderReview).where(OrderReview.id == review_id))
    review = query.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404,detail="Review not found")
    from app.dependencies.role_checker import is_global_user
    is_global = await is_global_user(db, current_user)
    if not is_global and review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only admin can delete other's reviews")
    await db.delete(review)
    await db.commit()
    return {"success": True,"message": "Review deleted successfully"}





@router.get("/{review_id}", response_model=ReviewResponseSchema)
async def get_one_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("reviews:view"))):
    query = await db.execute(select(OrderReview).where(OrderReview.id == review_id))
    review = query.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404,detail="Review not found")
    return review

