import base64
import json
import time
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.models import Chat, User
from app.db.session import get_db
from app.repositories.chat_repo import ChatRepository
from app.schemas.chat_schema import AIRequest, ChatOut, MessageOut
from app.services.ai_service import AIService
from app.utils.limits import check_user_usage_limit, decrement_user_limit
from app.utils.pdf_extractor import PDFExtractionError, extract_text_from_pdf

router = APIRouter(prefix="/chat", tags=["chat"])
ai_service = AIService()


# 1. Naya Chat banana
@router.post("/new")
@limiter.limit("10/minute")
def create_chat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.create_chat(db, current_user.id)
    return {"chat_id": chat.id}


# 2. Saari Chats ki list
@router.get("/all", response_model=list[ChatOut])
@limiter.limit("30/minute")
def get_all_chats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ChatRepository.get_all_by_user(db, current_user.id)


# 3. Specific chat ki history
@router.get("/{chat_id}")
@limiter.limit("30/minute")
def get_chat_history(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = ChatRepository.get_history(db, chat_id, limit=50)
    return [
        {"role": m.role, "text": m.content, "image_data": m.image_data}
        for m in messages
    ]


# 4. Delete Chat
@router.delete("/{chat_id}")
@limiter.limit("10/minute")
def delete_chat(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = ChatRepository.delete_chat(db, chat_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Deleted"}


# 5. Update Chat Title
@router.put("/{chat_id}/title")
@limiter.limit("20/minute")
def update_chat_title(
    request: Request,
    chat_id: int,
    new_title: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    updated_chat = ChatRepository.update_title(db, chat_id, new_title)
    return {"id": updated_chat.id, "title": updated_chat.title}


# 6. Get Chat Details
@router.get("/details/{chat_id}")
@limiter.limit("30/minute")
def get_chat_details(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {
        "id": chat.id,
        "title": chat.title,
        "pdf_context": chat.pdf_context,
    }


# 7. AI Streaming (Strict protection limit)
@router.post("/stream")
@limiter.limit("15/minute")
async def ai_stream(
    request: Request,
    req: AIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == req.chat_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    clean_prompt = str(req.prompt)
    ChatRepository.add_message(db, req.chat_id, "user", clean_prompt, req.image_base64)
    history = ChatRepository.get_history(db, req.chat_id, limit=8)
    context_to_send = chat.pdf_context if chat.pdf_context else ""

    full_response = ai_service.process_request(
        user_id=current_user.id,
        prompt=clean_prompt,
        history=history,
        file_context=context_to_send,
        image_data=req.image_base64,
        task=req.task if hasattr(req, "task") else "general",
    )

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


# 8. PDF Upload (Strict File limit)
@router.post("/upload-pdf/{chat_id}")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    chat_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat nahi mili ya aap authorized nahi hain.",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Sirf PDF files upload karne ki ijazat hai."
        )

    try:
        content = await file.read()
        text = extract_text_from_pdf(content)
        ChatRepository.update_pdf_context(db, chat_id, text)

        return {
            "status": "success",
            "filename": file.filename,
            "message": "PDF successfully parse aur save ho gayi hai.",
        }

    except PDFExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Server par file process karte hue koi masla aya hai.",
        )


# 9. Cleanup Chat Messages
@router.delete("/{chat_id}/cleanup/{after_index}")
@limiter.limit("10/minute")
def cleanup_chat_messages(
    request: Request,
    chat_id: int,
    after_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(db, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    ChatRepository.delete_messages_after(db, chat_id, current_user.id, after_index)
    return {"message": "Database cleaned up successfully"}