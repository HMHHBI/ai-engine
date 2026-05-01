from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import time, json, base64

from app.db.session import get_db
from app.api.deps import get_current_user
from app.db.models import User
from app.schemas.chat_schema import AIRequest, ChatOut, MessageOut
from app.repositories.chat_repo import ChatRepository
from app.services.ai_service import AIService
from app.utils.pdf_extractor import extract_text_from_pdf
from app.utils.limits import check_user_usage_limit, decrement_user_limit

router = APIRouter(prefix="/chat", tags=["chat"])
ai_service = AIService()

# 1. Naya Chat banana (Frontend needs this!)
@router.post("/new")
def create_chat(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chat = ChatRepository.create_chat(db, current_user.id)
    return {"chat_id": chat.id}

# 2. Saari Chats ki list (Sidebar ke liye)
@router.get("/all", response_model=list[ChatOut])
def get_all_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ChatRepository.get_all_by_user(db, current_user.id)

# 3. Aik specific chat ki history (Frontend load hote hi ye call karta hai)
@router.get("/{chat_id}")
def get_chat_history(chat_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = ChatRepository.get_history(db, chat_id, limit=50) # Repository function use karein
    return [{"role": m.role, "text": m.content, "image_data": m.image_data} for m in messages]

# 4. Delete Chat
@router.delete("/{chat_id}")
def delete_chat(chat_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    success = ChatRepository.delete_chat(db, chat_id, current_user.id)
    if not success: raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Deleted"}

# 5. Update Chat Title (Frontend jab manual rename kare ya AI title generate kare)
@router.put("/{chat_id}/title")
def update_chat_title(
    chat_id: int, 
    new_title: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Security: Check user ownership
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    updated_chat = ChatRepository.update_title(db, chat_id, new_title)
    return {"id": updated_chat.id, "title": updated_chat.title}

# 6. Get Chat Details (PDF context aur baqi info ke liye)
@router.get("/details/{chat_id}")
def get_chat_details(
    chat_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {
        "id": chat.id,
        "title": chat.title,
        "pdf_context": chat.pdf_context,
    }
    
# 7. AI Streaming (The main engine)
@router.post("/stream")
async def ai_stream(req: AIRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chat = ChatRepository.get_by_id(db, req.chat_id, current_user.id)
    if not chat: raise HTTPException(status_code=404, detail="Chat not found")

    # Limit check
    if "image" in req.prompt.lower():
        check_user_usage_limit(current_user, "image")

    # Save user msg
    # img_data = json.dumps(req.image_base64) if req.image_base64 else None
    ChatRepository.add_message(db, req.chat_id, "user", req.prompt, req.image_base64)

    # Gemini logic (Make sure process_request is updated in ai_service.py)
    history = ChatRepository.get_history(db, req.chat_id, limit=11)
    full_response = ai_service.process_request(req.prompt, history, chat.pdf_context, req.image_base64)

    # Update Title if it's a new chat
    if chat.title == "New Chat":
        new_title = ai_service.generate_chat_title(req.prompt)
        ChatRepository.update_title(db, chat.id, new_title)

    def generate():
        res_text = full_response if full_response else "AI Error"
        if "![" in res_text:
            decrement_user_limit(db, current_user, "image")
            yield res_text
        else:
            for chunk in res_text.split(" "):
                yield chunk + " "
                time.sleep(0.01)
        
        ChatRepository.add_message(db, req.chat_id, "ai", res_text)

    return StreamingResponse(generate(), media_type="text/plain")

# 8. PDF Upload
@router.post("/upload-pdf/{chat_id}")
async def upload_pdf(chat_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text = extract_text_from_pdf(content)
    ChatRepository.update_pdf_context(db, chat_id, text)
    return {"text": text, "filename": file.filename}

# app/api/chat.py

@router.delete("/{chat_id}/cleanup/{after_index}")
def cleanup_chat_messages(
    chat_id: int, 
    after_index: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    # Pehle check karo ke chat is user ki hai ya nahi (Security)
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Messages delete karo jo is index ke baad hain
    ChatRepository.delete_messages_after(db, chat_id, current_user.id, after_index)
    return {"message": "Database cleaned up successfully"}