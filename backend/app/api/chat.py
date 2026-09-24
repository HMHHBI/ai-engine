from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from contextlib import suppress
from typing import Any, Optional

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
from app.core.stream_concurrency import acquire_stream_lease, release_stream_lease
from starlette.background import BackgroundTask
from app.db.models import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.chat_schema import (
    AIRequest,
    ChatCreate,
    ChatDetailsOut,
    ChatOut,
    ChatPersonaUpdate,
)
from app.services.chat_service import ChatApplicationService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.embedding_service import EmbeddingService
from app.services.reranker_service import (
    RerankCandidate,
    RerankerService,
    create_reranker_provider,
)
from app.services.providers.errors import (
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
)
from app.services.providers.factory import (
    LLMProviderFactory,
    MODEL_REGISTRY,
)
from app.storage import build_document_key, get_storage_backend
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
# Helpers & Persona Prompts
# ============================================================

MODEL_ALIASES: dict[str, AIModel] = {
    "ollama-llama3.2": AIModel.OLLAMA_LLAMA_3_2,
    "ollama-deepseek-r1": AIModel.OLLAMA_DEEPSEEK_R1,
    "openai-gpt-4o-mini": AIModel.OPENAI_GPT_4O_MINI,
    "gemini-2.5-flash": AIModel.GEMINI_2_5_FLASH,
}

PERSONA_PROMPTS: dict[str, str] = {
    "default": (
        "Adopt a direct, balanced, and professional tone. Provide structured and clear answers."
    ),
    "academic": (
        "Adopt the persona of a rigorous Academic Researcher. "
        "Use precise analytical terminology, emphasize logical deduction, maintain objective tone, "
        "and structure your reasoning with scholarly clarity."
    ),
    "developer": (
        "Adopt the persona of an expert Senior Software Engineer. "
        "Be concise, prioritize idiomatic code and architectural best practices, highlight edge cases, "
        "and avoid fluff."
    ),
    "legal": (
        "Adopt the persona of a meticulous Legal Analyst. "
        "Pay strict attention to exact wording, definitions, conditions, obligations, and exceptions. "
        "Differentiate clearly between explicit statements and potential interpretations."
    ),
    "simple": (
        "Adopt the persona of a clear and friendly Explainer. "
        "Explain complex ideas using simple, plain English, relatable analogies, and concise sentences."
    ),
}


RERANK_INITIAL_K = 20
RERANK_FINAL_K = 6


def _build_rerank_candidates(
    chunks: list[dict[str, Any]],
) -> list[RerankCandidate]:
    return [
        RerankCandidate(
            chunk_id=int(chunk["id"]),
            content=str(chunk["content"]),
            score=float(chunk.get("rrf_score", chunk.get("score", 0.0))),
            metadata={
                "id": chunk["id"],
                "document_id": chunk.get("document_id"),
                "page_number": chunk.get("page_number"),
                "chunk_index": chunk.get("chunk_index"),
                "distance": chunk.get("distance"),
                "rrf_score": chunk.get("rrf_score"),
                "score": chunk.get("score"),
            },
        )
        for chunk in chunks
    ]


def _build_system_prompt(
    persona: str,
    custom_instructions: Optional[str],
    context_str: Optional[str],
) -> str:
    parts: list[str] = [
        "You are Hassan AI Engine, an intelligent, document-grounded assistant."
    ]

    persona_key = persona.strip().lower() if persona else "default"
    persona_rule = PERSONA_PROMPTS.get(persona_key, PERSONA_PROMPTS["default"])
    parts.append(f"ROLE & TONE GUIDELINES:\n{persona_rule}")

    if custom_instructions and custom_instructions.strip():
        parts.append(
            f"USER CUSTOM INSTRUCTIONS:\n"
            f"Adhere strictly to the following user instructions:\n{custom_instructions.strip()}"
        )

    if context_str:
        parts.append(
            "RULES:\n"
            "1. Answer document questions strictly from the retrieved context.\n"
            "2. Do not invent, speculate, or extrapolate facts beyond what is written.\n"
            "3. Do not use general knowledge to fill gaps in the document.\n"
            "4. Preserve the exact distinction between headings, goals, practices, examples, activities, explanations, and tests.\n"
            "5. Do not combine separate statements merely because they occur in the same process area.\n"
            "6. Treat temporal words such as before, after, during, then, and next as strict constraints.\n"
            "7. Do not infer a temporal relationship unless the retrieved context explicitly supports it.\n"
            "8. If the user asks for an explicit list, use the list supported by the document rather than constructing a new list from nearby statements.\n"
            "9. If the retrieved context is insufficient, state that the relevant information was not retrieved instead of guessing.\n"
            "10. When useful, mention the document page supporting the answer.\n"
            "11. Never mention internal phrases like 'retrieved context', 'chunk', 'vector distance', or 'database' in your response.\n"
            "12. Adopt a natural, professional tone. If citing a page, cite it naturally (e.g. 'According to page 1...').\n\n"
            "RETRIEVED DOCUMENT CONTEXT:\n\n"
            f"{context_str}"
        )
    else:
        parts.append(
            "The user is asking about an uploaded document, "
            "but no sufficiently relevant document context was retrieved for this question.\n\n"
            "Do not answer using general knowledge.\n"
            "Do not guess.\n"
            "Do not invent information from the document.\n"
            "Tell the user that the relevant information was not retrieved from the uploaded document."
        )

    return "\n\n---\n\n".join(parts)


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


@router.post("/new", response_model=ChatOut)
@limiter.limit("10/minute")
def create_chat(
    request: Request,
    payload: Optional[ChatCreate] = None,
    current_user: User = Depends(get_current_user),
):
    try:
        title = payload.title if payload and payload.title else "New Chat"
        persona = payload.persona if payload else "default"
        custom_instructions = payload.custom_instructions if payload else None

        chat = ChatRepository.create_chat(
            user_id=current_user.id,
            title=title,
            persona=persona,
            custom_instructions=custom_instructions,
        )
        return chat
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
                "id": message.id,
                "role": message.role,
                "text": message.content,
                "image_data": message.image_data,
                "sources": message.sources,
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
# 4. Update Chat Persona / Custom Instructions
# ============================================================


@router.patch("/{chat_id}/persona", response_model=ChatOut)
@limiter.limit("20/minute")
def update_chat_persona(
    request: Request,
    chat_id: int,
    payload: ChatPersonaUpdate,
    current_user: User = Depends(get_current_user),
):
    try:
        updated_chat = ChatRepository.update_persona_and_instructions(
            chat_id=chat_id,
            user_id=current_user.id,
            persona=payload.persona,
            custom_instructions=payload.custom_instructions,
        )

        if updated_chat is None:
            raise HTTPException(
                status_code=404,
                detail="Chat not found.",
            )

        return updated_chat
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to update persona chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update persona settings.",
        )


# ============================================================
# 5. Delete Chat
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
# 6. Update Chat Title
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
# 7. Get Chat Details
# ============================================================


@router.get("/details/{chat_id}", response_model=ChatDetailsOut)
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

        return chat
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
# 8. AI Streaming + RAG + Persona Prompt Layering
# ============================================================


async def _heartbeat_stream(
    source: AsyncIterator[str],
    request: Request,
    heartbeat_interval: float | None = None,
) -> AsyncIterator[str]:
    interval = heartbeat_interval if heartbeat_interval is not None else settings.HEARTBEAT_INTERVAL_SECONDS
    source_iterator = source.__aiter__()
    next_task = asyncio.create_task(source_iterator.__anext__())

    try:
        while True:
            done, _ = await asyncio.wait(
                {next_task},
                timeout=interval,
            )

            if done:
                try:
                    chunk = next_task.result()
                except StopAsyncIteration:
                    return

                yield chunk
                next_task = asyncio.create_task(source_iterator.__anext__())
                continue

            if await request.is_disconnected():
                return

            yield ": keep-alive\n\n"
    finally:
        if not next_task.done():
            next_task.cancel()

        with suppress(asyncio.CancelledError, StopAsyncIteration):
            await next_task

        with suppress(asyncio.CancelledError):
            await source_iterator.aclose()


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

    lease_token = await acquire_stream_lease(current_user.id)
    if not lease_token:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "AI_STREAM_CONCURRENCY_LIMIT",
                "message": "An AI stream is already active for this user.",
            },
        )

    try:
        return await _execute_ai_stream(
            request=request,
            req=req,
            current_user=current_user,
            clean_prompt=clean_prompt,
            lease_token=lease_token,
            request_started_at=request_started_at,
        )
    except Exception:
        await release_stream_lease(current_user.id, lease_token)
        raise


async def _execute_ai_stream(
    *,
    request: Request,
    req: AIRequest,
    current_user: User,
    clean_prompt: str,
    lease_token: str,
    request_started_at: float,
) -> AsyncIterator[str]:
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
            image_mime_list=req.image_mime,
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

    active_document = None
    if chat.pdf_context:
        if req.document_id is not None:
            active_document = await asyncio.to_thread(
                DocumentRepository.get_ready_for_chat,
                document_id=req.document_id,
                chat_id=req.chat_id,
                user_id=current_user.id,
            )
            if active_document is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found.",
                )
        else:
            active_document = await asyncio.to_thread(
                DocumentRepository.get_active_for_chat,
                chat_id=req.chat_id,
                user_id=current_user.id,
            )

    logger.info(
        "ai_provider_selected",
        extra={
            "event": "ai_provider_selected",
            "chat_id": req.chat_id,
            "provider": ai_provider.value,
            "model": ai_model.value,
            "persona": getattr(chat, "persona", "default"),
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
                    has_legacy_context = bool(getattr(chat, "pdf_context", None))
                    context_chunks = []

                    if active_document is not None or has_legacy_context:
                        doc_id = (
                            active_document.id
                            if active_document is not None
                            else req.chat_id
                        )

                        query_vector = await EmbeddingService.generate_embedding(
                            req.prompt,
                            model_provider=embedding_provider.value,
                        )

                        if query_vector:
                            retrieval_top_k = (
                                RERANK_INITIAL_K
                                if settings.ENABLE_RERANKING
                                else RERANK_FINAL_K
                            )

                            context_chunks = await asyncio.to_thread(
                                VectorRepository.search_hybrid_chunks,
                                user_id=current_user.id,
                                document_id=doc_id,
                                query_text=req.prompt,
                                query_vector=query_vector,
                                top_k=retrieval_top_k,
                                max_distance=0.70,
                                adaptive_margin=0.15,
                            )

                            if settings.ENABLE_RERANKING and context_chunks:
                                rerank_candidates = _build_rerank_candidates(context_chunks)
                                try:
                                    reranker = RerankerService(
                                        provider=create_reranker_provider()
                                    )
                                    reranked_candidates = await asyncio.to_thread(
                                        reranker.rerank,
                                        req.prompt,
                                        rerank_candidates,
                                        RERANK_FINAL_K,
                                    )
                                    reranked_chunks: list[dict[str, Any]] = []
                                    for candidate in reranked_candidates:
                                        metadata = dict(candidate.metadata or {})
                                        reranked_chunks.append(
                                            {
                                                "id": int(metadata["id"]),
                                                "document_id": metadata.get("document_id"),
                                                "content": candidate.content,
                                                "page_number": metadata.get("page_number"),
                                                "chunk_index": metadata.get("chunk_index"),
                                                "distance": float(
                                                    metadata.get("distance", 0.0)
                                                ),
                                                "rrf_score": metadata.get("rrf_score"),
                                                "score": candidate.score,
                                            }
                                        )
                                    context_chunks = reranked_chunks

                                    logger.info(
                                        "rag_reranking_completed",
                                        extra={
                                            "event": "rag_reranking_completed",
                                            "chat_id": req.chat_id,
                                            "candidate_count": len(rerank_candidates),
                                            "final_count": len(context_chunks),
                                            "strategy": "hybrid_rerank",
                                        },
                                    )
                                except Exception as rerank_err:
                                    logger.warning(
                                        "rag_reranking_fallback_triggered",
                                        extra={
                                            "event": "rag_reranking_fallback_triggered",
                                            "chat_id": req.chat_id,
                                            "error": str(rerank_err),
                                            "fallback_strategy": "hybrid_top_k",
                                        },
                                    )
                                    context_chunks = context_chunks[:RERANK_FINAL_K]

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

        context_str = None
        if context_chunks:
            context_parts: list[str] = []
            for chunk in context_chunks:
                page_info = (
                    f" (Page {chunk['page_number']})"
                    if chunk.get("page_number") is not None
                    else ""
                )
                source_block = f"[Document Passage{page_info}]\n{chunk['content']}"
                context_parts.append(source_block)

            context_str = "\n\n---\n\n".join(context_parts)

        # Dynamic Layered System Prompt
        system_prompt = _build_system_prompt(
            persona=getattr(chat, "persona", "default"),
            custom_instructions=getattr(chat, "custom_instructions", None),
            context_str=context_str if (chat.pdf_context and context_chunks) else None,
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
                "document_id": (
                    int(chunk["document_id"])
                    if chunk.get("document_id") is not None
                    else None
                ),
                "page_number": (
                    int(chunk["page_number"])
                    if chunk.get("page_number") is not None
                    else None
                ),
                "chunk_index": (
                    int(chunk["chunk_index"])
                    if chunk.get("chunk_index") is not None
                    else None
                ),
                "distance": float(chunk.get("distance", 0.0)),
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
                elapsed_stream_s = time.monotonic() - stream_started_at
                if elapsed_stream_s > settings.AI_STREAM_MAX_DURATION_SECONDS:
                    logger.warning(
                        "ai_stream_max_duration_exceeded",
                        extra={
                            "event": "ai_stream_max_duration_exceeded",
                            "chat_id": req.chat_id,
                            "elapsed_s": round(elapsed_stream_s, 2),
                            "max_duration_s": settings.AI_STREAM_MAX_DURATION_SECONDS,
                        },
                    )
                    raise AIProviderTimeout(
                        f"Stream exceeded maximum allowed duration of {settings.AI_STREAM_MAX_DURATION_SECONDS}s"
                    )

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

        # 4. Persistence (Only upon successful generation)
        persisted_message = None
        if full_text.strip():
            try:
                persisted_message = await asyncio.to_thread(
                    ChatRepository.add_message,
                    chat_id=req.chat_id,
                    user_id=current_user.id,
                    role="ai",
                    content=full_text,
                    sources=sources if context_chunks else None,
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

    async def stream_with_lease():
        try:
            async for chunk in event_generator():
                yield chunk
        finally:
            await release_stream_lease(current_user.id, lease_token)

    return StreamingResponse(
        _heartbeat_stream(stream_with_lease(), request),
        media_type="text/event-stream",
        background=BackgroundTask(release_stream_lease, current_user.id, lease_token),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-AI-Provider": ai_provider.value,
            "X-AI-Model": ai_model.value,
        },
    )


# ============================================================
# 9. Hardened Document Upload & Ingestion
# ============================================================


@router.post("/upload-pdf/{chat_id}")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    chat_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    document = None
    storage_key = None
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

        semaphore = DocumentIngestionService.get_embedding_semaphore()

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
                detail="Document embedding failed. Existing document was not changed.",
            )

        # 1. Physical Storage Save before DB entity creation
        storage = get_storage_backend()
        storage_key = build_document_key(user_id=current_user.id)

        try:
            content_stream = io.BytesIO(content)
            await asyncio.to_thread(
                storage.save,
                storage_key,
                content_stream,
                content_type=file.content_type or "application/pdf",
            )
        except Exception:
            logger.exception(
                "Document storage failed before database creation. user_id=%s",
                current_user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document storage failed.",
            )

        # 2. Persist Document entity
        document = await asyncio.to_thread(
            DocumentRepository.create,
            user_id=current_user.id,
            chat_id=chat.id,
            filename=safe_filename,
            mime_type=file.content_type or "application/pdf",
            file_size=len(content),
            page_count=len(pages),
            storage_url=None,
            storage_key=storage_key,
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session missing or unauthorized.",
            )

        db_objs = await asyncio.to_thread(
            VectorRepository.replace_document_chunks,
            user_id=current_user.id,
            document_id=document.id,
            chunks_with_embeddings=chunks_with_embeddings,
            pdf_context=f"Indexed File: {safe_filename}",
        )

        await asyncio.to_thread(
            DocumentRepository.update_status,
            document_id=document.id,
            user_id=current_user.id,
            status="ready",
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
            "document": {
                "id": document.id,
                "chat_id": document.chat_id,
                "filename": document.filename,
                "mime_type": document.mime_type,
                "file_size": document.file_size,
                "page_count": document.page_count,
                "status": "ready",
            },
        }

    except HTTPException:
        if document:
            await asyncio.to_thread(
                DocumentRepository.mark_failed_and_cleanup,
                document_id=document.id,
                user_id=current_user.id,
                error_message="Document ingestion failed.",
            )
        if storage_key:
            try:
                storage = get_storage_backend()
                await asyncio.to_thread(storage.delete, storage_key)
            except Exception:
                pass
        raise

    except asyncio.CancelledError:
        if storage_key:
            try:
                storage = get_storage_backend()
                await asyncio.to_thread(storage.delete, storage_key)
            except Exception:
                pass
        raise

    except Exception:
        logger.exception(
            "Unexpected error in upload_pdf chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )
        if document:
            await asyncio.to_thread(
                DocumentRepository.mark_failed_and_cleanup,
                document_id=document.id,
                user_id=current_user.id,
                error_message="Server error during document ingestion.",
            )
        if storage_key:
            try:
                storage = get_storage_backend()
                await asyncio.to_thread(storage.delete, storage_key)
            except Exception:
                pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server error during document ingestion.",
        )


# ============================================================
# 10. Cleanup Chat Messages
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
