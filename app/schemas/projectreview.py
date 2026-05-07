from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CreateReviewSchema(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review: str


class UpdateReviewSchema(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    review: Optional[str] = None


class ReviewResponseSchema(BaseModel):
    id: str
    user_id: str
    rating: int
    review: str
    created_at: datetime

    class Config:
        from_attributes = True