from pydantic import BaseModel
from typing import Optional, List

# AI Response Request (Jo aapka purana AIRequest tha)
class AIRequest(BaseModel):
    chat_id: int
    prompt: str
    task: str = "general"
    file_context: Optional[str] = None
    image_base64: Optional[List[str]] = None
    image_mime: Optional[str] = "image/png"

# Message Format
class MessageOut(BaseModel):
    role: str
    text: str
    image_data: Optional[str] = None

    class Config:
        from_attributes = True

# Chat Info (Sidebar ke liye)
class ChatOut(BaseModel):
    id: int
    title: str

    class Config:
        from_attributes = True