import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class ProjectReview(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()))

    user_id: Mapped[str] = mapped_column(String(36),ForeignKey("auth_users.id", ondelete="CASCADE"))

    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    review: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow)

    updated_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)