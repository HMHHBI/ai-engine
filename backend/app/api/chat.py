from starlette.concurrency import run_in_threadpool
import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.db.models import Chat, User
from app.db.session import SessionLocal, get_db
from app.repositories.chat_repo import ChatRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.chat_schema import AIRequest, ChatOut
from app.services.embedding_service import EmbeddingService
from app.services.providers.factory import LLMProviderFactory
from app.utils.pdf_extractor import PDFExtractionError, extract_text_from_pdf

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================
# 1. Create New Chat
# ============================================================


@router.post("/new")
@limiter.limit("10/minute")
def create_chat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.create_chat(db, current_user.id)

    return {"chat_id": chat.id}


# ============================================================
# 2. Get All Chats
# ============================================================


@router.get("/all", response_model=list[ChatOut])
@limiter.limit("30/minute")
def get_all_chats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ChatRepository.get_all_by_user(
        db,
        current_user.id,
    )


# ============================================================
# 3. Get Specific Chat History
# ============================================================


@router.get("/{chat_id}")
@limiter.limit("30/minute")
def get_chat_history(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        db,
        chat_id,
        current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    messages = ChatRepository.get_history(
        db,
        chat_id,
        limit=50,
    )

    return [
        {
            "role": m.role,
            "text": m.content,
            "image_data": m.image_data,
        }
        for m in messages
    ]


# ============================================================
# 4. Delete Chat
# ============================================================


@router.delete("/{chat_id}")
@limiter.limit("10/minute")
def delete_chat(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = ChatRepository.delete_chat(
        db,
        chat_id,
        current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return {"message": "Deleted"}


# ============================================================
# 5. Update Chat Title
# ============================================================


@router.put("/{chat_id}/title")
@limiter.limit("20/minute")
def update_chat_title(
    request: Request,
    chat_id: int,
    new_title: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        db,
        chat_id,
        current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    updated_chat = ChatRepository.update_title(
        db,
        chat_id,
        new_title,
    )

    return {
        "id": updated_chat.id,
        "title": updated_chat.title,
    }


# ============================================================
# 6. Get Chat Details
# ============================================================


@router.get("/details/{chat_id}")
@limiter.limit("30/minute")
def get_chat_details(
    request: Request,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        db,
        chat_id,
        current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return {
        "id": chat.id,
        "title": chat.title,
        "pdf_context": chat.pdf_context,
    }


# ============================================================
# 7. AI Streaming + RAG
# ============================================================


@router.post("/stream")
@limiter.limit("15/minute")
async def ai_stream(
    request: Request,
    req: AIRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # --------------------------------------------------------
    # Verify chat ownership
    # --------------------------------------------------------

    chat = (
        db.query(Chat)
        .filter(
            Chat.id == req.chat_id,
            Chat.user_id == current_user.id,
        )
        .first()
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    clean_prompt = str(req.prompt).strip()

    # --------------------------------------------------------
    # Save user message
    # --------------------------------------------------------

    await run_in_threadpool(
        ChatRepository.add_message,
        db,
        req.chat_id,
        "user",
        clean_prompt,
        req.image_base64,
    )

    # --------------------------------------------------------
    # AI / Embedding configuration
    # --------------------------------------------------------

    ai_provider = chat.ai_provider or settings.DEFAULT_AI_PROVIDER
    ai_model = req.model or chat.ai_model or settings.DEFAULT_AI_MODEL
    embedding_provider = (
        chat.embedding_provider or settings.DEFAULT_EMBEDDING_PROVIDER
    )

    context_chunks: list[dict] = []

    # ========================================================
    # RAG
    # ========================================================

    # Only perform embedding + vector search if this chat
    # contains uploaded document context.

    if chat.pdf_context:
        query_vector = await EmbeddingService.generate_embedding(
            clean_prompt,
            model_provider=embedding_provider,
        )

        if query_vector:
            context_chunks = await run_in_threadpool(
                VectorRepository.search_similar_chunks,
                db=db,
                chat_id=req.chat_id,
                query_vector=query_vector,
                top_k=6,
                max_distance=0.40,
            )

            # ------------------------------------------------
            # RAG Debug Output
            # ------------------------------------------------

            print(
                "\n🔎 RAG RETRIEVED CONTEXT",
                flush=True,
            )

            for i, chunk in enumerate(
                context_chunks,
                start=1,
            ):
                print(
                    f"\n--- CHUNK {i} ---",
                    flush=True,
                )

                print(
                    f"Page: {chunk['page_number']}",
                    flush=True,
                )

                print(
                    f"Chunk Index: {chunk['chunk_index']}",
                    flush=True,
                )

                print(
                    f"Distance: {chunk['distance']:.6f}",
                    flush=True,
                )

                print(
                    chunk["content"][:1500],
                    flush=True,
                )

            print(
                "\n🔎 END RAG CONTEXT\n",
                flush=True,
            )

    # ========================================================
    # Build Grounded Context
    # ========================================================

    if context_chunks:

        context_parts = []

        for chunk in context_chunks:
            source_block = (
                f"[Source]\n"
                f"Page: {chunk['page_number']}\n"
                f"Chunk Index: {chunk['chunk_index']}\n"
                f"Vector Distance: {chunk['distance']:.6f}\n"
                f"Content:\n"
                f"{chunk['content']}"
            )

            context_parts.append(source_block)

        context_str = "\n\n---\n\n".join(context_parts)

        # ====================================================
        # Strict Document Grounding Prompt
        # ====================================================

        system_prompt = (
            "You are Hassan AI Engine, an intelligent "
            "document-grounded assistant.\n\n"
            "The user is asking questions about an uploaded "
            "document. The retrieved context below is the "
            "primary and authoritative source for document "
            "questions.\n\n"
            "IMPORTANT RULES:\n"
            "1. Answer document questions strictly from the "
            "retrieved document context.\n"
            "2. Do not invent facts that are not supported "
            "by the retrieved context.\n"
            "3. Do not use general knowledge to fill gaps "
            "in the document.\n"
            "4. Pay close attention to the exact wording "
            "of the document.\n"
            "5. Preserve the distinction between headings, "
            "goals, practices, examples, explanations, "
            "activities, and testing statements.\n"
            "6. Do not combine separate statements simply "
            "because they occur in the same process area.\n"
            "7. If the user asks about order or relationship "
            "such as 'before', 'after', 'during', 'before "
            "assembly', or 'after integration', follow the "
            "actual relationship described in the document.\n"
            "8. If the document explicitly lists items, "
            "prefer the explicit list rather than creating "
            "your own list from nearby sentences.\n"
            "9. If a statement is mentioned separately from "
            "the main goals, do not incorrectly present it "
            "as one of those goals.\n"
            "10. If the retrieved context is insufficient "
            "to answer the question, clearly say that the "
            "relevant information was not retrieved instead "
            "of guessing.\n"
            "11. Treat temporal words such as 'before', 'after', "
            "'during', 'then', and 'next' as strict constraints. "
            "Do not infer a temporal relationship unless the "
            "retrieved document explicitly supports it.\n"
            "12. Do not answer a question by combining separate "
            "sentences merely because they appear in the same "
            "process area. Each claim must be supported by the "
            "specific retrieved text.\n"
            "13. If the question asks 'what activities are performed "
            "before X', identify only activities explicitly described "
            "as occurring before X. Do not include activities that "
            "occur during or after X.\n"
            "14. If the retrieved context contains relevant information "
            "but does not explicitly establish the requested order or "
            "relationship, say that the document context does not "
            "explicitly establish that relationship.\n"
            "15. When answering a document question, prefer a concise "
            "answer directly supported by the retrieved passages over "
            "a broader explanation assembled from nearby information.\n"
            "16. When useful, mention the document page "
            "number supporting the answer.\n\n"
            "RETRIEVED DOCUMENT CONTEXT:\n\n"
            f"{context_str}"
        )

    else:

        # ====================================================
        # General AI Mode
        # ====================================================


        system_prompt = (
            "You are Hassan AI Engine, a document-grounded assistant.\n\n"
            "The user has uploaded a document and is asking questions "
            "in this document-grounded chat.\n\n"
            "No sufficiently relevant document context was retrieved "
            "for this question.\n\n"
            "IMPORTANT RULES:\n"
            "1. Do NOT answer using general knowledge.\n"
            "2. Do NOT guess.\n"
            "3. Do NOT invent information from the document.\n"
            "4. Clearly tell the user that the relevant information "
            "was not retrieved from the uploaded document.\n"
        )

    # ========================================================
    # AI Configuration Debug
    # ========================================================

    print(
        "\n🔥 AI CHAT CONFIG"
        f"\n   Provider: {ai_provider}"
        f"\n   Model: {ai_model}"
        f"\n   Embedding: {embedding_provider}\n",
        flush=True,
    )

    # ========================================================
    # Dynamic Provider Selection
    # ========================================================

    provider = LLMProviderFactory.get_provider(ai_model)

    # ========================================================
    # Auto Chat Title
    # ========================================================

    if chat.title == "New Chat":

        new_title = (
            clean_prompt[:25] + "..." if len(clean_prompt) > 25 else clean_prompt
        )

        ChatRepository.update_title(
            db,
            chat.id,
            new_title,
        )

    # ========================================================
    # SSE Streaming
    # ========================================================

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
                with SessionLocal() as stream_db:
                    await run_in_threadpool(
                        ChatRepository.add_message,
                        stream_db,
                        req.chat_id,
                        "ai",
                        full_text,
                    )

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-AI-Model": ai_model,
        },
    )


# ============================================================
# 8. PDF Upload & Ingestion
# ============================================================


@router.post("/upload-pdf/{chat_id}")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    chat_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        db,
        chat_id,
        current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat session missing or unauthorized.",
        )

    filename = file.filename.lower()

    if not filename.endswith((".pdf", ".txt", ".md", ".json")):
        raise HTTPException(
            status_code=400,
            detail=("Unsupported format. " "Allowed formats: .pdf, .txt, .md, .json"),
        )

    try:

        content = await file.read()

        # ----------------------------------------------------
        # 1. Text Extraction
        # ----------------------------------------------------

        if filename.endswith(".pdf"):

            pages = await run_in_threadpool(
                extract_text_from_pdf,
                content,
            )

            if not pages:
                raise HTTPException(
                    status_code=400,
                    detail=("PDF is empty or contains " "no readable text."),
                )

            has_text = any(page.text and page.text.strip() for page in pages)

            if not has_text:
                raise HTTPException(
                    status_code=400,
                    detail=("PDF contains no readable text."),
                )

        else:

            text = content.decode(
                "utf-8",
                errors="ignore",
            )

            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=("File is empty or contains " "no readable text."),
                )

        # ----------------------------------------------------
        # 3. Chunk Document
        # ----------------------------------------------------

        if filename.endswith(".pdf"):

            chunks = await run_in_threadpool(
                EmbeddingService.chunk_text,
                pages,
                500,
                50,
            )

        else:

            chunks = await run_in_threadpool(
                EmbeddingService.chunk_text,
                text,
                500,
                50,
            )

        # ----------------------------------------------------
        # 4. Generate Embeddings in Parallel
        # ----------------------------------------------------

        embedding_provider = (
            chat.embedding_provider or settings.DEFAULT_EMBEDDING_PROVIDER
        )

        semaphore = asyncio.Semaphore(4)

        async def generate_chunk_embedding(chunk):

            async with semaphore:

                return await EmbeddingService.generate_embedding(
                    chunk.text,
                    model_provider=embedding_provider,
                )

        vectors = await asyncio.gather(
            *[generate_chunk_embedding(chunk) for chunk in chunks]
        )

        chunks_with_embeddings = [
            (chunk, vector)
            for chunk, vector in zip(
                chunks,
                vectors,
            )
            if vector is not None
        ]

        failed_embeddings = len(chunks) - len(chunks_with_embeddings)

        # ----------------------------------------------------
        # 5. Store Chunks + Embeddings
        # ----------------------------------------------------

        if chunks_with_embeddings:

            db_objs = await run_in_threadpool(
                VectorRepository.replace_document_chunks,
                db=db,
                chat_id=chat_id,
                chunks_with_embeddings=chunks_with_embeddings,
                pdf_context=f"Indexed File: {file.filename}",
            )

            return {
                "status": "success",
                "filename": file.filename,
                "pdf_context": f"Indexed File: {file.filename}",
                "chunks_total": len(chunks),
                "chunks_indexed": len(db_objs),
                "chunks_failed": failed_embeddings,
                "message": (
                    f"Indexed "
                    f"{len(chunks_with_embeddings)} "
                    f"of {len(chunks)} chunks into pgvector."
                ),
            }

        else:

            raise HTTPException(
                status_code=500,
                detail=("Failed to generate " "chunk embeddings."),
            )

    except PDFExtractionError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=("Server error during ingestion: " f"{str(e)}"),
        )


# ============================================================
# 9. Cleanup Chat Messages
# ============================================================


@router.delete("/{chat_id}/cleanup/{after_index}")
@limiter.limit("10/minute")
def cleanup_chat_messages(
    request: Request,
    chat_id: int,
    after_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        db,
        chat_id,
        current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    ChatRepository.delete_messages_after(
        db,
        chat_id,
        current_user.id,
        after_index,
    )

    return {"message": "Database cleaned up successfully"}
