import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector  # RAG / Vector Embeddings

from app.db.session import Base


# Plan types
class UserPlan(enum.Enum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    PRO = "PRO"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    profile_image = Column(String, nullable=True)

    plan = Column(Enum(UserPlan), default=UserPlan.FREE)
    image_limit = Column(Integer, default=5)
    search_limit = Column(Integer, default=10)
    reset_token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    chats = relationship("Chat", back_populates="owner", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String, default="New Chat")
    pdf_context = Column(Text, nullable=True)

    ai_provider = Column(String, nullable=True)
    ai_model = Column(String, nullable=True)
    embedding_provider = Column(String, nullable=True)

    owner = relationship("User", back_populates="chats")
    messages = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )
    chunks = relationship(
        "DocumentChunk", back_populates="chat", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(
        Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)  # user / ai
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    image_data = Column(Text, nullable=True)  # Base64 storage

    chat = relationship("Chat", back_populates="messages")


class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    task = Column(String, nullable=False)
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(
        Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True)
    embedding = Column(Vector(768), nullable=True)  # 768 for Ollama nomic-embed / mxbai
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    chat = relationship("Chat", back_populates="chunks")
