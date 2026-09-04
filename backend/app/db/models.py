from __future__ import annotations

import enum
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserPlan(str, enum.Enum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    PRO = "PRO"


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False,
    )

    email = Column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )

    password = Column(
        String(255),
        nullable=False,
    )

    profile_image = Column(
        String(2048),
        nullable=True,
    )

    plan = Column(
        Enum(
            UserPlan,
            name="user_plan",
            native_enum=True,
        ),
        nullable=False,
        default=UserPlan.FREE,
        server_default=UserPlan.FREE.value,
    )

    image_limit = Column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )

    search_limit = Column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
    )

    # ----------------------------------------------------------
    # Password reset
    # ----------------------------------------------------------

    reset_token_hash = Column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
    )

    reset_token_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ----------------------------------------------------------
    # Account status
    # ----------------------------------------------------------

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    # ----------------------------------------------------------
    # Relationships
    # ----------------------------------------------------------

    chats = relationship(
        "Chat",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Chat(Base):
    __tablename__ = "chats"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title = Column(
        String(255),
        nullable=False,
        default="New Chat",
        server_default="New Chat",
    )

    pdf_context = Column(
        Text,
        nullable=True,
    )

    ai_provider = Column(
        String(50),
        nullable=True,
    )

    ai_model = Column(
        String(100),
        nullable=True,
    )

    embedding_provider = Column(
        String(50),
        nullable=True,
    )

    owner = relationship(
        "User",
        back_populates="chats",
    )

    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="chat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_chats_user_id_id",
            "user_id",
            "id",
        ),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    chat_id = Column(
        Integer,
        ForeignKey(
            "chats.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role = Column(
        String(20),
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    sources = Column(
        JSONB,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    image_data = Column(
        Text,
        nullable=True,
    )

    chat = relationship(
        "Chat",
        back_populates="messages",
    )

    __table_args__ = (
        Index(
            "ix_messages_chat_id_id",
            "chat_id",
            "id",
        ),
    )


class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    task = Column(
        String(100),
        nullable=False,
    )

    prompt = Column(
        Text,
        nullable=True,
    )

    response = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    chat_id = Column(
        Integer,
        ForeignKey(
            "chats.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    content = Column(
        Text,
        nullable=False,
    )

    page_number = Column(
        Integer,
        nullable=True,
        index=True,
    )

    chunk_index = Column(
        Integer,
        nullable=True,
    )

    embedding = Column(
        Vector(768),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    chat = relationship(
        "Chat",
        back_populates="chunks",
    )

    __table_args__ = (
        Index(
            "ix_document_chunks_chat_id_id",
            "chat_id",
            "id",
        ),
    )
