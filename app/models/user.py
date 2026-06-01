from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID
from sqlalchemy import String, Text, ForeignKey, DateTime, Enum, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password: Mapped[str] = mapped_column(String, nullable=False)


# class UserActiveStatus(Base):
#     __tablename__ = "active"
#     online_status: Mapped[bool] = mapped_column(default=False, nullable=False)
#     user_id: Mapped[UUID] = mapped_column(
#         Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
#     )
