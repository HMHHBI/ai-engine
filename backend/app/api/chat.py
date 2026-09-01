from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.config import (
    AIModel,
    AIProvider,
    EmbeddingProvider,
    settings,
)
from app.core.rate_limiter import limiter
from app.db.models import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.chat_schema import AIRequest, ChatOut
from app.services.embedding_service import EmbeddingService
from app.services.providers.factory import LLMProviderFactory
from app.utils.pdf_extractor import PDFExtractionError, extract_text_from_pdf

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


# ============================================================
# Helpers
# ============================================================

MODEL_ALIASES: dict[str, AIModel] = {
    "ollama-llama3.2": AIModel.OLLAMA_LLAMA_3_2,
    "ollama-deepseek-r1": AIModel.OLLAMA_DEEPSEEK_R1,
    "openai-gpt-4o-mini": AIModel.OPENAI_GPT_4O_MINI,
    "gemini-2.5-flash": AIModel.GEMINI_2_5_FLASH,
}


def _parse_ai_provider(value: str | AIProvider) -> AIProvider:
    """
    Normalize and validate an AI provider.
    """
    if isinstance(value, AIProvider):
        return value

    try:
        return AIProvider(str(value).strip().lower())
    except ValueError as exc:
        valid = ", ".join(provider.value for provider in AIProvider)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported AI provider '{value}'. " f"Supported providers: {valid}."
            ),
        ) from exc


def _parse_ai_model(value: str | AIModel) -> AIModel:
    """
    Normalize and validate an AI model (supporting legacy UI keys).
    """
    if isinstance(value, AIModel):
        return value

    cleaned = str(value).strip()

    if cleaned in MODEL_ALIASES:
        return MODEL_ALIASES[cleaned]

    try:
        return AIModel(cleaned)
    except ValueError as exc:
        valid = ", ".join(model.value for model in AIModel)
        raise HTTPException(
            status_code=400,
            detail=(f"Unsupported AI model '{value}'. " f"Supported models: {valid}."),
        ) from exc


def _parse_embedding_provider(
    value: str | EmbeddingProvider,
) -> EmbeddingProvider:
    """
    Normalize and validate an embedding provider.
    """
    if isinstance(value, EmbeddingProvider):
        return value

    try:
        return EmbeddingProvider(str(value).strip().lower())
    except ValueError as exc:
        valid = ", ".join(provider.value for provider in EmbeddingProvider)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported embedding provider '{value}'. "
                f"Supported providers: {valid}."
            ),
        ) from exc


def _resolve_ai_configuration(
    *,
    chat_provider: str | None,
    chat_model: str | None,
    requested_model: str | None,
) -> tuple[AIProvider, AIModel]:
    """
    Resolve the effective provider/model configuration.

    If requested_model is supplied, derive the matching provider from
    the model registry. Otherwise, fallback to the chat's stored provider
    or application default.
    """
    raw_model = requested_model or chat_model or settings.DEFAULT_AI_MODEL.value
    model = _parse_ai_model(raw_model)

    if requested_model:
        provider = None
        for candidate_provider in AIProvider:
            supported = LLMProviderFactory.get_supported_models(candidate_provider)
            if model in supported:
                provider = candidate_provider
                break

        if provider is None:
            raise HTTPException(
                status_code=400,
                detail=f"No provider is registered for model '{model.value}'.",
            )
    elif chat_provider:
        provider = _parse_ai_provider(chat_provider)
    else:
        provider = settings.DEFAULT_AI_PROVIDER

    try:
        provider, model = LLMProviderFactory.validate_configuration(
            provider=provider,
            model=model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return provider, model


# ============================================================
# 1. Create New Chat
# ============================================================


@router.post("/new")
@limiter.limit("10/minute")
def create_chat(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.create_chat(
        user_id=current_user.id,
    )

    return {
        "chat_id": chat.id,
    }


# ============================================================
# 2. Get All Chats
# ============================================================


@router.get(
    "/all",
    response_model=list[ChatOut],
)
@limiter.limit("30/minute")
def get_all_chats(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return ChatRepository.get_all_by_user(
        user_id=current_user.id,
    )


# ============================================================
# 3. Get Specific Chat History
# ============================================================


@router.get("/{chat_id}")
@limiter.limit("30/minute")
def get_chat_history(
    request: Request,
    chat_id: int,
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    messages = ChatRepository.get_history(
        chat_id=chat_id,
        limit=50,
    )

    return [
        {
            "role": message.role,
            "text": message.content,
            "image_data": message.image_data,
        }
        for message in messages
    ]


# ============================================================
# 4. Delete Chat
# ============================================================


@router.delete("/{chat_id}")
@limiter.limit("10/minute")
def delete_chat(
    request: Request,
    chat_id: int,
    current_user: User = Depends(get_current_user),
):
    success = ChatRepository.delete_chat(
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    return {
        "message": "Deleted",
    }


# ============================================================
# 5. Update Chat Title
# ============================================================


@router.put("/{chat_id}/title")
@limiter.limit("20/minute")
def update_chat_title(
    request: Request,
    chat_id: int,
    new_title: str,
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    updated_chat = ChatRepository.update_title(
        chat_id=chat_id,
        new_title=new_title,
    )

    if updated_chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
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
    current_user: User = Depends(get_current_user),
):
    chat = ChatRepository.get_by_id(
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    return {
        "id": chat.id,
        "title": chat.title,
        "pdf_context": chat.pdf_context,
        "ai_provider": chat.ai_provider,
        "ai_model": chat.ai_model,
        "embedding_provider": chat.embedding_provider,
    }


# ============================================================
# 7. AI Streaming + RAG
# ============================================================


@router.post("/stream")
@limiter.limit("15/minute")
async def ai_stream(
    request: Request,
    req: AIRequest,
    current_user: User = Depends(get_current_user),
):
    # --------------------------------------------------------
    # Validate prompt
    # --------------------------------------------------------

    clean_prompt = req.prompt.strip()

    if not clean_prompt:
        raise HTTPException(
            status_code=400,
            detail="Prompt cannot be empty.",
        )

    # --------------------------------------------------------
    # Verify chat ownership
    # --------------------------------------------------------

    chat = await asyncio.to_thread(
        ChatRepository.get_by_id,
        chat_id=req.chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    # --------------------------------------------------------
    # Resolve AI configuration
    # --------------------------------------------------------

    ai_provider, ai_model = _resolve_ai_configuration(
        chat_provider=chat.ai_provider,
        chat_model=chat.ai_model,
        requested_model=req.model,
    )

    # --------------------------------------------------------
    # Resolve embedding provider
    # --------------------------------------------------------

    raw_embedding_provider = (
        chat.embedding_provider or settings.DEFAULT_EMBEDDING_PROVIDER.value
    )

    embedding_provider = _parse_embedding_provider(raw_embedding_provider)

    # --------------------------------------------------------
    # Save user message
    # --------------------------------------------------------

    await asyncio.to_thread(
        ChatRepository.add_message,
        req.chat_id,
        "user",
        clean_prompt,
        req.image_base64,
    )

    # ========================================================
    # RAG
    # ========================================================

    context_chunks: list[dict[str, Any]] = []

    if chat.pdf_context:
        query_vector = await EmbeddingService.generate_embedding(
            clean_prompt,
            model_provider=embedding_provider.value,
        )

        if query_vector:
            context_chunks = await asyncio.to_thread(
                VectorRepository.search_similar_chunks,
                user_id=current_user.id,
                chat_id=req.chat_id,
                query_vector=query_vector,
                top_k=6,
                max_distance=0.70,
                adaptive_margin=0.15,
            )

    # ========================================================
    # Build System Prompt
    # ========================================================

    if context_chunks:
        context_parts: list[str] = []

        for chunk in context_chunks:
            source_block = (
                "[Source]\n"
                f"Page: {chunk['page_number']}\n"
                f"Chunk Index: {chunk['chunk_index']}\n"
                f"Vector Distance: {chunk['distance']:.6f}\n"
                "Content:\n"
                f"{chunk['content']}"
            )
            context_parts.append(source_block)

        context_str = "\n\n---\n\n".join(context_parts)

        system_prompt = (
            "You are Hassan AI Engine, an intelligent "
            "document-grounded assistant.\n\n"
            "The user is asking a question about an uploaded "
            "document. The retrieved context below is the "
            "authoritative source for document-specific claims.\n\n"
            "RULES:\n"
            "1. Answer document questions strictly from the "
            "retrieved context.\n"
            "2. Do not invent facts that are not supported "
            "by the retrieved context.\n"
            "3. Do not use general knowledge to fill gaps "
            "in the document.\n"
            "4. Preserve the exact distinction between "
            "headings, goals, practices, examples, "
            "activities, explanations, and tests.\n"
            "5. Do not combine separate statements merely "
            "because they occur in the same process area.\n"
            "6. Treat temporal words such as before, after, "
            "during, then, and next as strict constraints.\n"
            "7. Do not infer a temporal relationship unless "
            "the retrieved context explicitly supports it.\n"
            "8. If the user asks for an explicit list, use "
            "the list supported by the document rather than "
            "constructing a new list from nearby statements.\n"
            "9. If the retrieved context is insufficient, "
            "state that the relevant information was not "
            "retrieved instead of guessing.\n"
            "10. When useful, mention the document page "
            "supporting the answer.\n\n"
            "RETRIEVED DOCUMENT CONTEXT:\n\n"
            f"{context_str}"
        )
    else:
        system_prompt = (
            "You are Hassan AI Engine, a document-grounded assistant.\n\n"
            "The user is asking about an uploaded document, "
            "but no sufficiently relevant document context "
            "was retrieved for this question.\n\n"
            "Do not answer using general knowledge.\n"
            "Do not guess.\n"
            "Do not invent information from the document.\n"
            "Tell the user that the relevant information was "
            "not retrieved from the uploaded document."
        )

    # ========================================================
    # Provider
    # ========================================================

    try:
        provider = LLMProviderFactory.get_provider(
            provider=ai_provider,
            model=ai_model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    logger.info(
        "Starting AI stream chat_id=%s provider=%s model=%s "
        "embedding_provider=%s retrieved_chunks=%s",
        req.chat_id,
        ai_provider.value,
        ai_model.value,
        embedding_provider.value,
        len(context_chunks),
    )

    # ========================================================
    # Auto Chat Title
    # ========================================================

    if chat.title == "New Chat":
        new_title = (
            clean_prompt[:25] + "..." if len(clean_prompt) > 25 else clean_prompt
        )

        await asyncio.to_thread(
            ChatRepository.update_title,
            chat_id=chat.id,
            new_title=new_title,
        )

    # ========================================================
    # Streaming
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

        except Exception:
            logger.exception(
                "AI provider stream failed chat_id=%s provider=%s model=%s",
                req.chat_id,
                ai_provider.value,
                ai_model.value,
            )

            error_message = (
                "\n[The AI provider is temporarily unavailable. Please try again.]"
            )

            full_text += error_message
            yield error_message

        finally:
            if full_text.strip():
                try:
                    await asyncio.to_thread(
                        ChatRepository.add_message,
                        req.chat_id,
                        "ai",
                        full_text,
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist AI response chat_id=%s",
                        req.chat_id,
                    )

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-AI-Provider": ai_provider.value,
            "X-AI-Model": ai_model.value,
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
    current_user: User = Depends(get_current_user),
):
    chat = await asyncio.to_thread(
        ChatRepository.get_by_id,
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat session missing or unauthorized.",
        )

    filename = (file.filename or "").lower()
    allowed_extensions = (".pdf", ".txt", ".md", ".json")

    if not filename.endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Allowed formats: .pdf, .txt, .md, .json",
        )

    try:
        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="File is empty.",
            )

        if filename.endswith(".pdf"):
            pages = await run_in_threadpool(
                extract_text_from_pdf,
                content,
            )

            if not pages:
                raise HTTPException(
                    status_code=400,
                    detail="PDF is empty or contains no readable text.",
                )

            has_text = any(page.text and page.text.strip() for page in pages)

            if not has_text:
                raise HTTPException(
                    status_code=400,
                    detail="PDF contains no readable text.",
                )
        else:
            text = content.decode(
                "utf-8",
                errors="ignore",
            )

            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="File is empty or contains no readable text.",
                )

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

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No usable document chunks were produced.",
            )

        embedding_provider = _parse_embedding_provider(
            chat.embedding_provider or settings.DEFAULT_EMBEDDING_PROVIDER.value
        )

        semaphore = asyncio.Semaphore(4)

        async def generate_chunk_embedding(chunk):
            async with semaphore:
                return await EmbeddingService.generate_embedding(
                    chunk.text,
                    model_provider=embedding_provider.value,
                )

        vectors = await asyncio.gather(
            *[generate_chunk_embedding(chunk) for chunk in chunks]
        )

        chunks_with_embeddings = [
            (chunk, vector)
            for chunk, vector in zip(chunks, vectors)
            if vector is not None
        ]

        failed_embeddings = len(chunks) - len(chunks_with_embeddings)

        if not chunks_with_embeddings:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate chunk embeddings.",
            )

        db_objs = await asyncio.to_thread(
            VectorRepository.replace_document_chunks,
            user_id=current_user.id,
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
            "embedding_provider": embedding_provider.value,
            "message": (
                f"Indexed {len(chunks_with_embeddings)} "
                f"of {len(chunks)} chunks into pgvector."
            ),
        }

    except PDFExtractionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "Document ingestion failed chat_id=%s",
            chat_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Server error during document ingestion.",
        ) from exc


# ============================================================
# 9. Cleanup Chat Messages
# ============================================================


@router.delete("/{chat_id}/cleanup/{after_index}")
@limiter.limit("10/minute")
def cleanup_chat_messages(
    request: Request,
    chat_id: int,
    after_index: int,
    current_user: User = Depends(get_current_user),
):
    success = ChatRepository.delete_messages_after(
        chat_id=chat_id,
        user_id=current_user.id,
        after_index=after_index,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Chat not found.",
        )

    return {
        "message": "Messages cleaned up successfully.",
    }
