from __future__ import annotations

import enum
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserPlan(str, enum.Enum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    PRO = "PRO"


class DocumentJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    token_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    chats = relationship(
        "Chat",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    documents = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    jobs = relationship(
        "DocumentJob",
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

    persona = Column(
        String(50),
        nullable=False,
        default="default",
        server_default="default",
    )

    custom_instructions = Column(
        Text,
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

    documents = relationship(
        "Document",
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


class Document(Base):
    __tablename__ = "documents"

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

    chat_id = Column(
        Integer,
        ForeignKey(
            "chats.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    filename = Column(
        String(255),
        nullable=False,
    )

    mime_type = Column(
        String(100),
        nullable=False,
    )

    file_size = Column(
        BigInteger,
        nullable=True,
    )

    page_count = Column(
        Integer,
        nullable=True,
    )

    storage_url = Column(
        Text,
        nullable=True,
    )

    storage_key = Column(
        Text,
        nullable=True,
        unique=True,
        index=True,
    )

    status = Column(
        String(20),
        nullable=False,
        default="processing",
        server_default="processing",
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    owner = relationship(
        "User",
        back_populates="documents",
    )

    chat = relationship(
        "Chat",
        back_populates="documents",
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    jobs = relationship(
        "DocumentJob",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_documents_chat_id_id",
            "chat_id",
            "id",
        ),
    )


class DocumentJob(Base):
    __tablename__ = "document_jobs"

    id = Column(
        BigInteger,
        primary_key=True,
    )

    document_id = Column(
        Integer,
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
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

    status = Column(
        String(20),
        nullable=False,
        default=DocumentJobStatus.QUEUED.value,
        server_default=DocumentJobStatus.QUEUED.value,
    )

    attempt = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    max_attempts = Column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )

    idempotency_key = Column(
        String(128),
        nullable=False,
        unique=True,
    )

    worker_id = Column(
        String(128),
        nullable=True,
    )

    queued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    heartbeat_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancel_requested_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    owner = relationship(
        "User",
        back_populates="jobs",
    )

    document = relationship(
        "Document",
        back_populates="jobs",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed', 'cancelled')",
            name="ck_document_jobs_valid_status",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="ck_document_jobs_attempt_non_negative",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="ck_document_jobs_max_attempts_positive",
        ),
        CheckConstraint(
            "attempt <= max_attempts",
            name="ck_document_jobs_attempt_lte_max",
        ),
        Index(
            "ix_document_jobs_user_id_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_document_jobs_status_queued_at",
            "status",
            "queued_at",
        ),
        Index(
            "ix_document_jobs_status_heartbeat_at",
            "status",
            "heartbeat_at",
        ),
        Index(
            "uq_document_jobs_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chat_id = Column(
        Integer, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id = Column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider = Column(String(32), nullable=False, index=True)
    model = Column(String(128), nullable=False, index=True)
    operation = Column(String(64), nullable=False, default="chat")
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    usage_source = Column(String(32), nullable=False, default="provider_reported")
    status = Column(String(32), nullable=False, default="succeeded")
    cost_amount = Column(Numeric(18, 8), nullable=True)
    cost_currency = Column(String(3), nullable=True, default="USD")
    pricing_version = Column(String(64), nullable=True)
    pricing_snapshot = Column(JSON, nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_ai_usage_events_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_ai_usage_events_output_tokens_non_negative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_ai_usage_events_total_tokens_non_negative",
        ),
        CheckConstraint(
            "cost_amount IS NULL OR cost_amount >= 0",
            name="ck_ai_usage_events_cost_non_negative",
        ),
        Index("ix_ai_usage_events_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_events_chat_created", "chat_id", "created_at"),
        Index(
            "ix_ai_usage_events_provider_model_created",
            "provider",
            "model",
            "created_at",
        ),
    )


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(32), nullable=False, index=True)
    model = Column(String(128), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    input_rate_per_million = Column(Numeric(18, 8), nullable=False)
    output_rate_per_million = Column(Numeric(18, 8), nullable=False)
    cached_input_rate_per_million = Column(Numeric(18, 8), nullable=True)
    pricing_version = Column(String(64), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_until = Column(DateTime(timezone=True), nullable=True)
    source_reference = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "input_rate_per_million >= 0",
            name="ck_model_pricing_input_rate_non_negative",
        ),
        CheckConstraint(
            "output_rate_per_million >= 0",
            name="ck_model_pricing_output_rate_non_negative",
        ),
        CheckConstraint(
            "cached_input_rate_per_million IS NULL OR cached_input_rate_per_million >= 0",
            name="ck_model_pricing_cached_rate_non_negative",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_model_pricing_effective_range",
        ),
        UniqueConstraint(
            "provider",
            "model",
            "pricing_version",
            name="uq_model_pricing_provider_model_version",
        ),
        Index(
            "ix_model_pricing_lookup",
            "provider",
            "model",
            "effective_from",
            "effective_until",
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

    document_id = Column(
        Integer,
        ForeignKey(
            "documents.id",
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
    )

    document = relationship(
        "Document",
        back_populates="chunks",
    )

    __table_args__ = (
        Index(
            "ix_document_chunks_chat_id_id",
            "chat_id",
            "id",
        ),
        Index(
            "ix_document_chunks_document_id_id",
            "document_id",
            "id",
        ),
    )
