from pydantic import BaseModel
from typing import Optional
from app.models.consigeereview import ReviewStatus



class ProductReviewCreate(BaseModel):
    order_id: str
    review: str
    rating: str



class ProductReviewApprove(BaseModel):
    status: ReviewStatus
    admin_comment: Optional[str] = None




class ProductReviewResponse(BaseModel):
    id: str
    order_id: str
    auth_users_id: str
    review: str
    rating: str
    status: ReviewStatus

    class Config:
        from_attributes = True
        
        
        
 
from pydantic import BaseModel
from typing import List, Optional    
class ApprovedReviewOut(BaseModel):
    id: str
    order_id: str
    auth_users_id: str
    review: str
    rating: str
    status: str
    admin_comment: Optional[str]
    admin_approved: bool

    class Config:
        from_attributes = True    
    
    
class ApprovedReviewPaginationResponse(BaseModel):
    total_reviews: int
    total_pages: int
    current_page: int
    limit: int
    data: List[ApprovedReviewOut]  
    

class ProductReviewOut(BaseModel):
    id: str
    order_id: str
    auth_users_id: str
    review: str
    rating: str
    status: str
    admin_comment: Optional[str]
    admin_approved: bool

    class Config:
        from_attributes = True


class ProductReviewPaginationResponse(BaseModel):
    total_reviews: int
    total_pages: int
    current_page: int
    limit: int
    data: List[ProductReviewOut]
            