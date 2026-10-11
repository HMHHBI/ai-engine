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
    func,
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
    
    created_workspaces = relationship(
        "Workspace",
        back_populates="creator",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    workspace_memberships = relationship(
        "WorkspaceMembership",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    workspace_documents_added = relationship(
        "WorkspaceDocument",
        back_populates="added_by_user",
        passive_deletes=True,
    )
    
    requested_research_runs = relationship(
        "ResearchRun",
        back_populates="requester",
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
    
    workspace_associations = relationship(
        "WorkspaceDocument",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    
    research_associations = relationship(
        "ResearchRunDocument",
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
        nullable=False,
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
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_doc_chunk_idx",
        ),
        Index(
            "ix_document_chunks_content_fts",
            func.to_tsvector(text("'english'"), content),
            postgresql_using="gin",
        ),
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    creator = relationship(
        "User",
        back_populates="created_workspaces",
    )

    memberships = relationship(
        "WorkspaceMembership",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    document_associations = relationship(
        "WorkspaceDocument",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    
    research_runs = relationship(
        "ResearchRun",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_workspaces_created_by_id", "created_by", "id"),)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    id = Column(Integer, primary_key=True)

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role = Column(
        String(20),
        nullable=False,
        default="researcher",
        server_default="researcher",
    )

    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    workspace = relationship(
        "Workspace",
        back_populates="memberships",
    )

    user = relationship(
        "User",
        back_populates="workspace_memberships",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'researcher', 'viewer')",
            name="ck_workspace_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'invited')",
            name="ck_workspace_memberships_status",
        ),
        Index(
            "ix_workspace_memberships_workspace_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_workspace_memberships_user_status",
            "user_id",
            "status",
        ),
    )


class WorkspaceDocument(Base):
    __tablename__ = "workspace_documents"

    id = Column(Integer, primary_key=True)

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    added_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    added_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    workspace = relationship(
        "Workspace",
        back_populates="document_associations",
    )

    document = relationship(
        "Document",
        back_populates="workspace_associations",
    )

    added_by_user = relationship(
        "User",
        back_populates="workspace_documents_added",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "document_id",
            name="uq_workspace_documents_workspace_document",
        ),
        Index(
            "ix_workspace_documents_workspace_added",
            "workspace_id",
            "added_at",
        ),
        Index(
            "ix_workspace_documents_document",
            "document_id",
        ),
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id = Column(Integer, primary_key=True)

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    requester_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    query = Column(Text, nullable=False)

    status = Column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
    )

    answer = Column(JSONB, nullable=True)

    run_metadata = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    completed_at = Column(DateTime(timezone=True), nullable=True)

    workspace = relationship(
        "Workspace",
        back_populates="research_runs",
    )

    requester = relationship(
        "User",
        back_populates="requested_research_runs",
    )

    document_associations = relationship(
        "ResearchRunDocument",
        back_populates="research_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_research_runs_valid_status",
        ),
        CheckConstraint(
            "length(trim(query)) > 0",
            name="ck_research_runs_query_nonempty",
        ),
        Index(
            "ix_research_runs_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_research_runs_requester_created",
            "requester_id",
            "created_at",
        ),
        Index(
            "ix_research_runs_workspace_status",
            "workspace_id",
            "status",
        ),
    )


class ResearchRunDocument(Base):
    __tablename__ = "research_run_documents"

    id = Column(Integer, primary_key=True)

    research_run_id = Column(
        Integer,
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    provenance = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    research_run = relationship(
        "ResearchRun",
        back_populates="document_associations",
    )

    document = relationship(
        "Document",
        back_populates="research_associations",
    )

    __table_args__ = (
        UniqueConstraint(
            "research_run_id",
            "document_id",
            name="uq_research_run_documents_run_document",
        ),
        Index(
            "ix_research_run_documents_document",
            "document_id",
        ),
    )

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    resource_type = Column(String(60), nullable=False)
    resource_id = Column(String(60), nullable=True)
    outcome = Column(String(20), nullable=False, default="success")  # success, failure, denied
    metadata_payload = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_action_created", "action", "created_at"),
    )
