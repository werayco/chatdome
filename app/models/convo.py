from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID
from sqlalchemy import String, Text, ForeignKey, DateTime, Enum, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7
from app.db.base import Base


class ConversationType(str, PyEnum):
    DM = "dm"
    GROUP = "group"


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    type: Mapped[ConversationType] = mapped_column(Enum(ConversationType), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    members: Mapped[list["ConversationMember"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_user_admin: Mapped[Optional[bool]] = mapped_column(nullable=True, default=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )
