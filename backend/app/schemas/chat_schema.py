from typing import List, Optional

from pydantic import BaseModel


# AI Stream Request Schema
class AIRequest(BaseModel):
    chat_id: int
    prompt: str
    task: str = "general"
    model: Optional[str] = None
    provider: Optional[str] = None
    file_context: Optional[str] = None
    image_base64: Optional[List[str]] = None  # List of Base64 strings or URLs
    image_mime: Optional[List[str]] = None  # Mapped mime types per image


# Message Out Schema (For Chat History / Streaming Output)
class MessageOut(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str  # FIX: Changed 'text' to 'content' to match Database Model
    image_data: Optional[str] = None  # JSON string of Cloudinary URLs

    class Config:
        from_attributes = True


# Chat Summary Schema (For Sidebar / Chat List)
class ChatOut(BaseModel):
    id: int
    title: str

    class Config:
        from_attributes = True
