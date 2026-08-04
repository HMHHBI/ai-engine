import asyncio
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.models import Chat, User
from app.db.session import get_db
from app.repositories.chat_repo import ChatRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.chat_schema import AIRequest, ChatOut
from app.services.embedding_service import EmbeddingService
from app.services.providers.factory import LLMProviderFactory
from app.utils.pdf_extractor import PDFExtractionError, extract_text_from_pdf

router = APIRouter(prefix="/chat", tags=["chat"])


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


# 7. AI Streaming (Multi-Provider Factory + pgvector RAG)
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

    clean_prompt = str(req.prompt).strip()

    # A. User Prompt DB Persistence
    ChatRepository.add_message(db, req.chat_id, "user", clean_prompt, req.image_base64)

    # B. Vector Similarity Search on pgvector
    query_vector = await EmbeddingService.generate_embedding(clean_prompt)
    context_chunks = []
    if query_vector:
        context_chunks = VectorRepository.search_similar_chunks(
            db=db, chat_id=req.chat_id, query_vector=query_vector, top_k=4
        )

    # Hybrid Prompt Strategy
    if context_chunks:
        context_str = "\n---\n".join(context_chunks)
        system_prompt = (
            "You are Hassan AI Engine, an intelligent production assistant. "
            "Below is the retrieved context from the uploaded document. "
            "If the user's question directly relates to this context, use it to form an accurate answer. "
            "HOWEVER, if the user's question is unrelated to the context (e.g. asking about general knowledge, flowers, science, everyday topics), "
            "IGNORE the context entirely and answer the user's question directly using your general knowledge.\n\n"
            f"Retrieved Document Context:\n{context_str}"
        )
    else:
        system_prompt = (
            "You are Hassan AI Engine, an intelligent production assistant. "
            "Answer the user's question accurately and helpfully using your general knowledge."
        )

    # C. Dynamic Provider Selection via Factory
    requested_model = req.model if req.model else "ollama-llama3.2"
    provider = LLMProviderFactory.get_provider(requested_model)

    # D. Auto Title Update
    if chat.title == "New Chat":
        new_title = (
            clean_prompt[:25] + "..." if len(clean_prompt) > 25 else clean_prompt
        )
        ChatRepository.update_title(db, chat.id, new_title)

    # E. SSE Response Streaming
    async def event_generator():
        full_text = ""
        try:
            async for token in provider.generate_stream(
                prompt=clean_prompt,
                system_prompt=system_prompt,
            ):
                full_text += token
                yield token
        except Exception as e:
            error_msg = f"\n[Provider Execution Error: {str(e)}]"
            full_text += error_msg
            yield error_msg
        finally:
            if full_text:
                ChatRepository.add_message(db, req.chat_id, "ai", full_text)

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 8. PDF Upload & Ingestion (Unified Chunking & Vector Store Logic)
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
            detail="Chat session missing or unauthorized.",
        )

    filename = file.filename.lower()
    if not filename.endswith((".pdf", ".txt", ".md", ".json")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Allowed formats: .pdf, .txt, .md, .json",
        )

    try:
        content = await file.read()

        # Extract Text
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(content)
        else:
            text = content.decode("utf-8", errors="ignore")

        if not text.strip():
            raise HTTPException(
                status_code=400, detail="File is empty or contains no readable text."
            )

        # 1. Update minimal metadata in Chat
        ChatRepository.update_pdf_context(db, chat_id, f"Indexed File: {file.filename}")

        # 2. Text Chunking
        chunks = EmbeddingService.chunk_text(text, chunk_size=500, overlap=50)

        # 3. Parallel Vector Embedding Generation
        vectors = await asyncio.gather(
            *[EmbeddingService.generate_embedding(c) for c in chunks]
        )

        chunks_with_embeddings = [
            (chunk, vector)
            for chunk, vector in zip(chunks, vectors)
            if vector is not None
        ]

        # 4. Save Chunks to VectorRepository
        if chunks_with_embeddings:
            db_objs = VectorRepository.store_document_chunks(
                db=db, chat_id=chat_id, chunks_with_embeddings=chunks_with_embeddings
            )
            return {
                "status": "success",
                "filename": file.filename,
                "chunks_indexed": len(db_objs),
                "message": f"Successfully indexed {len(db_objs)} chunks into pgvector.",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to generate chunk embeddings."
            )

    except PDFExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Server error during ingestion: {str(e)}",
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