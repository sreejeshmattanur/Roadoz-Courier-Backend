
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Enum,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from app.core.database import Base

class ReviewStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class ProductReview(Base):
    __tablename__ = "product_reviews"

    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36),ForeignKey("orders.id", ondelete="CASCADE"),nullable=False)
    auth_users_id = Column(String(36),ForeignKey("auth_users.id", ondelete="CASCADE"),nullable=False)
    review = Column(Text, nullable=False)
    rating = Column(String(10), nullable=False)
    status = Column(Enum(ReviewStatus),default=ReviewStatus.PENDING)
    admin_comment = Column(Text, nullable=True)
    created_at = Column(DateTime,default=datetime.utcnow)
    admin_approved = Column(Boolean, nullable=True, default=False)
    updated_at = Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    order = relationship("Order", backref="product_reviews")
    consignee = relationship("AuthUser", backref="product_reviews")