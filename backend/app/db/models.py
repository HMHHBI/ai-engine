from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.db.session import Base
from datetime import datetime
import enum

# Plan types ko barqarar rakhein
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

    chats = relationship("Chat", back_populates="owner")

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="New Chat")
    pdf_context = Column(Text, nullable=True)
    
    owner = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    role = Column(String)  # user / ai
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    image_data = Column(Text, nullable=True) # Base64 storage ke liye
    
    chat = relationship("Chat", back_populates="messages")

class AILog(Base):
    __tablename__ = "ai_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    task = Column(String)
    prompt = Column(Text)
    response = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)