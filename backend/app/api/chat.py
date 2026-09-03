from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.config import (
    AIModel,
    AIProvider,
    EmbeddingProvider,
    settings,
)
from app.core.error_codes import ErrorCode, SAFE_CLIENT_MESSAGES
from app.core.rate_limiter import limiter
from app.db.models import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.chat_schema import AIRequest, ChatOut
from app.services.chat_service import ChatApplicationService
from app.services.embedding_service import EmbeddingService
from app.services.providers.errors import (
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
)
from app.services.providers.factory import (
    LLMProviderFactory,
    MODEL_REGISTRY,
)
from app.utils.file_validation import (
    read_upload_with_limit,
    sanitize_filename,
    validate_content_type,
    validate_extension,
    validate_pdf_signature,
)
from app.utils.pdf_extractor import PDFExtractionError, PDFPage, extract_text_from_pdf

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
    if isinstance(value, AIProvider):
        return value

    try:
        return AIProvider(str(value).strip().lower())
    except ValueError as exc:
        valid = ", ".join(provider.value for provider in AIProvider)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported AI provider '{value}'. Supported providers: {valid}.",
        ) from exc


def _parse_ai_model(value: str | AIModel) -> AIModel:
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
            detail=f"Unsupported AI model '{value}'. Supported models: {valid}.",
        ) from exc


def _parse_embedding_provider(
    value: str | EmbeddingProvider,
) -> EmbeddingProvider:
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
    requested_provider: str | None,
    requested_model: str | None,
) -> tuple[AIProvider, AIModel]:
    if requested_model is not None:
        model = _parse_ai_model(requested_model)

        if requested_provider is not None:
            provider = _parse_ai_provider(requested_provider)
        else:
            definition = MODEL_REGISTRY.get(model)

            if definition is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported AI model '{model.value}'.",
                )

            provider = definition.provider

        try:
            return LLMProviderFactory.validate_configuration(
                provider=provider,
                model=model,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    if requested_provider is not None:
        provider = _parse_ai_provider(requested_provider)
        model = _parse_ai_model(chat_model or settings.DEFAULT_AI_MODEL.value)

        try:
            return LLMProviderFactory.validate_configuration(
                provider=provider,
                model=model,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    model = _parse_ai_model(chat_model or settings.DEFAULT_AI_MODEL.value)

    provider = (
        _parse_ai_provider(chat_provider)
        if chat_provider
        else settings.DEFAULT_AI_PROVIDER
    )

    try:
        return LLMProviderFactory.validate_configuration(
            provider=provider,
            model=model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


# ============================================================
# 1. Create New Chat
# ============================================================


@router.post("/new")
@limiter.limit("10/minute")
def create_chat(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    try:
        chat = ChatRepository.create_chat(
            user_id=current_user.id,
        )
        return {
            "chat_id": chat.id,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create chat user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create new chat session.",
        )


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
    try:
        return ChatRepository.get_all_by_user(
            user_id=current_user.id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch chats user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch chat history.",
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
    try:
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
            user_id=current_user.id,
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
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to get chat history chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch messages.",
        )


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
    try:
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
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to delete chat chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete chat.",
        )


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
    try:
        updated_chat = ChatRepository.update_title(
            chat_id=chat_id,
            user_id=current_user.id,
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
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to update title chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update chat title.",
        )


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
    try:
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
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to get chat details chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch chat details.",
        )


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
    request_started_at = time.monotonic()

    logger.info(
        "chat_request_started",
        extra={
            "event": "chat_request_started",
            "chat_id": req.chat_id,
        },
    )

    clean_prompt = req.prompt.strip()

    if not clean_prompt:
        raise HTTPException(
            status_code=400,
            detail="Prompt cannot be empty.",
        )

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

    ai_provider, ai_model = _resolve_ai_configuration(
        chat_provider=chat.ai_provider,
        chat_model=chat.ai_model,
        requested_provider=req.provider,
        requested_model=req.model,
    )

    raw_embedding_provider = (
        chat.embedding_provider or settings.DEFAULT_EMBEDDING_PROVIDER.value
    )
    embedding_provider = _parse_embedding_provider(raw_embedding_provider)

    new_title = None
    if chat.title == "New Chat":
        new_title = (
            clean_prompt[:25] + "..." if len(clean_prompt) > 25 else clean_prompt
        )

    try:
        prepared_message = await ChatApplicationService.prepare_chat_turn(
            chat_id=req.chat_id,
            user_id=current_user.id,
            content=clean_prompt,
            new_title=new_title,
            image_data_list=req.image_base64,
        )
    except ValueError as exc:
        logger.warning(
            "Failed to prepare chat turn chat_id=%s user_id=%s",
            req.chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception(
            "Failed to prepare chat turn chat_id=%s user_id=%s",
            req.chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to prepare chat message.",
        )

    if prepared_message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found.",
        )

    context_chunks: list[dict[str, Any]] = []

    if chat.pdf_context:
        query_vector = await EmbeddingService.generate_embedding(
            clean_prompt,
            model_provider=embedding_provider.value,
        )

        if query_vector:
            rag_started_at = time.monotonic()

            logger.info(
                "rag_retrieval_started",
                extra={
                    "event": "rag_retrieval_started",
                    "chat_id": req.chat_id,
                },
            )

            try:
                context_chunks = await asyncio.to_thread(
                    VectorRepository.search_similar_chunks,
                    user_id=current_user.id,
                    chat_id=req.chat_id,
                    query_vector=query_vector,
                    top_k=6,
                    max_distance=0.70,
                    adaptive_margin=0.15,
                )
            except Exception:
                logger.exception(
                    "rag_retrieval_failed",
                    extra={
                        "event": "rag_retrieval_failed",
                        "chat_id": req.chat_id,
                        "duration_ms": round(
                            (time.monotonic() - rag_started_at) * 1000,
                            2,
                        ),
                    },
                )
                raise

            logger.info(
                "rag_retrieval_completed",
                extra={
                    "event": "rag_retrieval_completed",
                    "chat_id": req.chat_id,
                    "retrieved_chunk_count": len(context_chunks),
                    "duration_ms": round(
                        (time.monotonic() - rag_started_at) * 1000,
                        2,
                    ),
                },
            )

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
            "1. Answer document questions strictly from the retrieved context.\n"
            "2. Do not invent facts that are not supported by the retrieved context.\n"
            "3. Do not use general knowledge to fill gaps in the document.\n"
            "4. Preserve the exact distinction between headings, goals, practices, examples, activities, explanations, and tests.\n"
            "5. Do not combine separate statements merely because they occur in the same process area.\n"
            "6. Treat temporal words such as before, after, during, then, and next as strict constraints.\n"
            "7. Do not infer a temporal relationship unless the retrieved context explicitly supports it.\n"
            "8. If the user asks for an explicit list, use the list supported by the document rather than constructing a new list from nearby statements.\n"
            "9. If the retrieved context is insufficient, state that the relevant information was not retrieved instead of guessing.\n"
            "10. When useful, mention the document page supporting the answer.\n\n"
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
        "ai_provider_selected",
        extra={
            "event": "ai_provider_selected",
            "chat_id": req.chat_id,
            "provider": ai_provider.value,
            "model": ai_model.value,
        },
    )

    # --------------------------------------------------------
    # Structured SSE stream
    # --------------------------------------------------------

    async def event_generator():
        full_text = ""
        chunk_count = 0
        first_token_at: float | None = None
        stream_started_at = time.monotonic()

        logger.info(
            "ai_stream_started",
            extra={
                "event": "ai_stream_started",
                "chat_id": req.chat_id,
                "provider": ai_provider.value,
                "model": ai_model.value,
            },
        )

        # 1. Config event
        yield _sse_event(
            "stream_started",
            {
                "provider": ai_provider.value,
                "model": ai_model.value,
            },
        )

        # 2. Structured RAG provenance
        sources = [
            {
                "id": int(chunk["id"]),
                "page_number": (
                    int(chunk["page_number"])
                    if chunk["page_number"] is not None
                    else None
                ),
                "chunk_index": (
                    int(chunk["chunk_index"])
                    if chunk["chunk_index"] is not None
                    else None
                ),
                "distance": float(chunk["distance"]),
            }
            for chunk in context_chunks
        ]

        yield _sse_event(
            "sources",
            {
                "sources": sources,
            },
        )

        # 3. Generate stream
        try:
            async for token in provider.generate_stream(
                prompt=clean_prompt,
                system_prompt=system_prompt,
            ):
                if await request.is_disconnected():
                    logger.info(
                        "ai_stream_cancelled",
                        extra={
                            "event": "ai_stream_cancelled",
                            "chat_id": req.chat_id,
                            "provider": ai_provider.value,
                            "model": ai_model.value,
                            "chunk_count": chunk_count,
                            "duration_ms": round(
                                (time.monotonic() - stream_started_at) * 1000,
                                2,
                            ),
                            "cancellation_reason": "client_disconnect",
                        },
                    )
                    raise asyncio.CancelledError

                if not token:
                    continue

                if first_token_at is None:
                    first_token_at = time.monotonic()

                    logger.info(
                        "ai_first_token",
                        extra={
                            "event": "ai_first_token",
                            "chat_id": req.chat_id,
                            "provider": ai_provider.value,
                            "model": ai_model.value,
                            "time_to_first_token_ms": round(
                                (first_token_at - stream_started_at) * 1000,
                                2,
                            ),
                        },
                    )

                chunk_count += 1
                full_text += token

                yield _sse_event(
                    "chunk",
                    {
                        "text": token,
                    },
                )

        except asyncio.CancelledError:
            logger.info(
                "ai_stream_cancelled",
                extra={
                    "event": "ai_stream_cancelled",
                    "chat_id": req.chat_id,
                    "provider": ai_provider.value,
                    "model": ai_model.value,
                    "chunk_count": chunk_count,
                    "duration_ms": round(
                        (time.monotonic() - stream_started_at) * 1000,
                        2,
                    ),
                    "cancellation_reason": ErrorCode.CANCELLED.value,
                },
            )
            yield _sse_event(
                "stream_cancelled",
                {
                    "message": SAFE_CLIENT_MESSAGES[ErrorCode.CANCELLED],
                },
            )
            raise

        except AIProviderTimeout:
            logger.warning(
                "ai_stream_failed",
                extra={
                    "event": "ai_stream_failed",
                    "chat_id": req.chat_id,
                    "provider": ai_provider.value,
                    "model": ai_model.value,
                    "chunk_count": chunk_count,
                    "duration_ms": round(
                        (time.monotonic() - stream_started_at) * 1000,
                        2,
                    ),
                    "error_code": ErrorCode.PROVIDER_TIMEOUT.value,
                },
            )
            yield _sse_event(
                "stream_error",
                {
                    "code": ErrorCode.PROVIDER_TIMEOUT.value,
                    "message": SAFE_CLIENT_MESSAGES[ErrorCode.PROVIDER_TIMEOUT],
                },
            )
            return

        except AIProviderUnavailable:
            logger.warning(
                "ai_stream_failed",
                extra={
                    "event": "ai_stream_failed",
                    "chat_id": req.chat_id,
                    "provider": ai_provider.value,
                    "model": ai_model.value,
                    "chunk_count": chunk_count,
                    "duration_ms": round(
                        (time.monotonic() - stream_started_at) * 1000,
                        2,
                    ),
                    "error_code": ErrorCode.PROVIDER_UNAVAILABLE.value,
                },
            )
            yield _sse_event(
                "stream_error",
                {
                    "code": ErrorCode.PROVIDER_UNAVAILABLE.value,
                    "message": SAFE_CLIENT_MESSAGES[ErrorCode.PROVIDER_UNAVAILABLE],
                },
            )
            return

        except AIProviderError:
            logger.exception(
                "ai_stream_failed",
                extra={
                    "event": "ai_stream_failed",
                    "chat_id": req.chat_id,
                    "provider": ai_provider.value,
                    "model": ai_model.value,
                    "chunk_count": chunk_count,
                    "duration_ms": round(
                        (time.monotonic() - stream_started_at) * 1000,
                        2,
                    ),
                    "error_code": ErrorCode.PROVIDER_ERROR.value,
                },
            )
            yield _sse_event(
                "stream_error",
                {
                    "code": ErrorCode.PROVIDER_ERROR.value,
                    "message": SAFE_CLIENT_MESSAGES[ErrorCode.PROVIDER_ERROR],
                },
            )
            return

        except Exception:
            logger.exception(
                "ai_stream_failed",
                extra={
                    "event": "ai_stream_failed",
                    "chat_id": req.chat_id,
                    "provider": ai_provider.value,
                    "model": ai_model.value,
                    "chunk_count": chunk_count,
                    "duration_ms": round(
                        (time.monotonic() - stream_started_at) * 1000,
                        2,
                    ),
                    "error_code": ErrorCode.STREAM_ERROR.value,
                },
            )
            yield _sse_event(
                "stream_error",
                {
                    "code": ErrorCode.STREAM_ERROR.value,
                    "message": SAFE_CLIENT_MESSAGES[ErrorCode.STREAM_ERROR],
                },
            )
            return

        # 4. Persistence
        persisted_message = None
        if full_text.strip():
            try:
                persisted_message = await asyncio.to_thread(
                    ChatRepository.add_message,
                    chat_id=req.chat_id,
                    user_id=current_user.id,
                    role="ai",
                    content=full_text,
                )

                if persisted_message is None:
                    logger.error(
                        "chat_request_failed",
                        extra={
                            "event": "chat_request_failed",
                            "chat_id": req.chat_id,
                            "provider": ai_provider.value,
                            "model": ai_model.value,
                            "duration_ms": round(
                                (time.monotonic() - request_started_at) * 1000,
                                2,
                            ),
                            "error_code": ErrorCode.PERSISTENCE_ERROR.value,
                        },
                    )
                    yield _sse_event(
                        "stream_error",
                        {
                            "code": ErrorCode.PERSISTENCE_ERROR.value,
                            "message": SAFE_CLIENT_MESSAGES[
                                ErrorCode.PERSISTENCE_ERROR
                            ],
                        },
                    )
                    return

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "chat_request_failed",
                    extra={
                        "event": "chat_request_failed",
                        "chat_id": req.chat_id,
                        "provider": ai_provider.value,
                        "model": ai_model.value,
                        "duration_ms": round(
                            (time.monotonic() - request_started_at) * 1000,
                            2,
                        ),
                        "error_code": ErrorCode.PERSISTENCE_ERROR.value,
                    },
                )
                yield _sse_event(
                    "stream_error",
                    {
                        "code": ErrorCode.PERSISTENCE_ERROR.value,
                        "message": SAFE_CLIENT_MESSAGES[ErrorCode.PERSISTENCE_ERROR],
                    },
                )
                return

        # 5. Terminal event
        stream_duration_ms = round(
            (time.monotonic() - stream_started_at) * 1000,
            2,
        )

        logger.info(
            "ai_stream_completed",
            extra={
                "event": "ai_stream_completed",
                "chat_id": req.chat_id,
                "provider": ai_provider.value,
                "model": ai_model.value,
                "chunk_count": chunk_count,
                "duration_ms": stream_duration_ms,
            },
        )

        logger.info(
            "chat_request_completed",
            extra={
                "event": "chat_request_completed",
                "chat_id": req.chat_id,
                "provider": ai_provider.value,
                "model": ai_model.value,
                "duration_ms": round(
                    (time.monotonic() - request_started_at) * 1000,
                    2,
                ),
            },
        )

        yield _sse_event(
            "stream_completed",
            {
                "message_id": (
                    persisted_message.id
                    if full_text.strip() and persisted_message is not None
                    else None
                ),
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-AI-Provider": ai_provider.value,
            "X-AI-Model": ai_model.value,
        },
    )


# ============================================================
# 8. Hardened Document Upload & Ingestion
# ============================================================


@router.post("/upload-pdf/{chat_id}")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    chat_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    try:
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

        safe_filename = sanitize_filename(file.filename)
        extension = validate_extension(safe_filename)
        validate_content_type(extension, file.content_type)

        content = await read_upload_with_limit(file)

        if extension == ".pdf":
            validate_pdf_signature(content)

            try:
                pages = await run_in_threadpool(
                    extract_text_from_pdf,
                    content,
                )
            except PDFExtractionError:
                logger.warning(
                    "PDF rejected during extraction chat_id=%s user_id=%s",
                    chat_id,
                    current_user.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The uploaded document could not be processed.",
                )
        else:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Text file must be valid UTF-8.",
                ) from exc

            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="File is empty or contains no readable text.",
                )

            pages = [PDFPage(page_number=1, text=text)]

        chunks = await run_in_threadpool(
            EmbeddingService.chunk_text,
            pages,
            500,
            50,
        )

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No usable document chunks were produced.",
            )

        if len(chunks) > settings.MAX_DOCUMENT_CHUNKS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Document produces too many chunks for processing.",
            )

        if len(chunks) > settings.MAX_CHUNK_EMBEDDINGS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Document exceeds the maximum embedding workload.",
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

        if failed_embeddings > 0 or len(chunks_with_embeddings) != len(chunks):
            logger.error(
                "Document ingestion aborted: %s/%s chunk embeddings failed. "
                "Preserving previous chat state. chat_id=%s user_id=%s",
                failed_embeddings,
                len(chunks),
                chat_id,
                current_user.id,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Document embedding failed. " "Existing document was not changed."
                ),
            )

        db_objs = await asyncio.to_thread(
            VectorRepository.replace_document_chunks,
            user_id=current_user.id,
            chat_id=chat_id,
            chunks_with_embeddings=chunks_with_embeddings,
            pdf_context=f"Indexed File: {safe_filename}",
        )

        return {
            "status": "success",
            "filename": safe_filename,
            "pdf_context": f"Indexed File: {safe_filename}",
            "chunks_total": len(chunks),
            "chunks_indexed": len(db_objs),
            "chunks_failed": 0,
            "embedding_provider": embedding_provider.value,
            "message": (
                f"Indexed {len(chunks_with_embeddings)} "
                f"of {len(chunks)} chunks into pgvector."
            ),
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Unexpected error in upload_pdf chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server error during document ingestion.",
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
    current_user: User = Depends(get_current_user),
):
    try:
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

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Failed to cleanup messages chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to cleanup messages.",
        )
