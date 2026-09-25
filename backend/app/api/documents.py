from __future__ import annotations

import asyncio
import io
import logging
import uuid
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.config import EmbeddingProvider, settings
from app.db.models import User
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_job_repo import (
    DocumentJobRepository,
    DocumentJobTransitionError,
)
from app.repositories.document_repo import DocumentRepository
from app.schemas.document_schema import (
    DocumentJobOut,
    DocumentLifecycleOut,
    DocumentMetadataUpdate,
    DocumentOut,
)
from app.services.document_lifecycle_service import DocumentLifecycleService
from app.storage import build_document_key, get_storage_backend
from app.utils.file_validation import (
    read_upload_with_limit,
    sanitize_filename,
    validate_content_type,
    validate_extension,
    validate_pdf_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


def _job_to_response(job) -> DocumentJobOut:
    return DocumentJobOut(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _get_latest_job(
    document_id: int,
    user_id: int,
):
    with session_scope() as db:
        return DocumentJobRepository(db).get_latest_for_document(
            document_id=document_id,
            user_id=user_id,
        )


def _document_with_job(
    document,
    user_id: int,
) -> DocumentLifecycleOut:
    job = _get_latest_job(document.id, user_id)

    return DocumentLifecycleOut(
        id=document.id,
        user_id=document.user_id,
        chat_id=document.chat_id,
        filename=document.filename,
        mime_type=document.mime_type,
        file_size=document.file_size,
        page_count=document.page_count,
        storage_url=document.storage_url,
        status=document.status,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
        job=_job_to_response(job) if job else None,
    )


@router.post(
    "/chat/{chat_id}/upload",
    response_model=DocumentLifecycleOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    chat_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Create and process a first-class research document.

    The existing durable DocumentJob infrastructure is used for execution
    state. The uploaded object is retained in durable storage when ingestion
    fails so that the document can be retried without another upload.
    """
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session missing or unauthorized.",
            )

        safe_filename = sanitize_filename(file.filename)
        extension = validate_extension(safe_filename)
        validate_content_type(extension, file.content_type)

        content = await read_upload_with_limit(file)

        if extension == ".pdf":
            validate_pdf_signature(content)

        storage = get_storage_backend()
        storage_key = build_document_key(user_id=current_user.id)

        await asyncio.to_thread(
            storage.save,
            storage_key,
            io.BytesIO(content),
            content_type=file.content_type or "application/pdf",
        )

        document = await asyncio.to_thread(
            DocumentRepository.create,
            user_id=current_user.id,
            chat_id=chat.id,
            filename=safe_filename,
            mime_type=file.content_type or "application/pdf",
            file_size=len(content),
            page_count=None,
            storage_url=None,
            storage_key=storage_key,
            status="processing",
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session missing or unauthorized.",
            )

        job = await asyncio.to_thread(
            DocumentLifecycleService.create_job,
            document_id=document.id,
            user_id=current_user.id,
        )

        embedding_provider = (
            chat.embedding_provider
            or settings.DEFAULT_EMBEDDING_PROVIDER.value
        )

        try:
            parsed_embedding_provider = EmbeddingProvider(
                str(embedding_provider).strip().lower()
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported embedding provider.",
            ) from exc

        await DocumentLifecycleService.process_job(
            document_id=document.id,
            user_id=current_user.id,
            job_id=job.id,
            embedding_provider=parsed_embedding_provider,
            content=content,
        )

        refreshed = await asyncio.to_thread(
            DocumentRepository.get_owned_document,
            document_id=document.id,
            user_id=current_user.id,
        )

        return _document_with_job(
            refreshed,
            current_user.id,
        )

    except HTTPException:
        if document is None and storage_key:
            try:
                await asyncio.to_thread(
                    get_storage_backend().delete,
                    storage_key,
                )
            except Exception:
                logger.exception(
                    "Failed to clean up orphaned document storage."
                )
        raise

    except Exception as exc:
        logger.exception(
            "Document lifecycle upload failed chat_id=%s user_id=%s",
            chat_id,
            current_user.id,
        )

        if document is None and storage_key:
            try:
                await asyncio.to_thread(
                    get_storage_backend().delete,
                    storage_key,
                )
            except Exception:
                logger.exception(
                    "Failed to clean up orphaned document storage."
                )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed.",
        ) from exc


@router.post(
    "/{document_id}/retry",
    response_model=DocumentLifecycleOut,
    status_code=status.HTTP_200_OK,
)
async def retry_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
):
    document = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document_id,
        user_id=current_user.id,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or unauthorized.",
        )

    if document.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed documents can be retried.",
        )

    if not document.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document source is no longer available for retry.",
        )

    active_job = _get_latest_job(
        document_id=document.id,
        user_id=current_user.id,
    )

    if active_job and active_job.status in {"queued", "processing"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already being processed.",
        )

    chat = await asyncio.to_thread(
        ChatRepository.get_by_id,
        chat_id=document.chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or unauthorized.",
        )

    try:
        embedding_provider = EmbeddingProvider(
            str(
                chat.embedding_provider
                or settings.DEFAULT_EMBEDDING_PROVIDER.value
            )
            .strip()
            .lower()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported embedding provider.",
        ) from exc

    await asyncio.to_thread(
        DocumentRepository.update_status,
        document_id=document.id,
        user_id=current_user.id,
        status="processing",
    )

    job = await asyncio.to_thread(
        DocumentLifecycleService.create_job,
        document_id=document.id,
        user_id=current_user.id,
    )

    try:
        await DocumentLifecycleService.process_job(
            document_id=document.id,
            user_id=current_user.id,
            job_id=job.id,
            embedding_provider=embedding_provider,
        )
    except Exception as exc:
        logger.warning(
            "Document retry failed document_id=%s user_id=%s",
            document_id,
            current_user.id,
        )

        refreshed = await asyncio.to_thread(
            DocumentRepository.get_owned_document,
            document_id=document.id,
            user_id=current_user.id,
        )

        if refreshed is not None:
            return _document_with_job(
                refreshed,
                current_user.id,
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document retry failed.",
        ) from exc

    refreshed = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document.id,
        user_id=current_user.id,
    )

    return _document_with_job(
        refreshed,
        current_user.id,
    )


@router.get(
    "/chat/{chat_id}",
    response_model=List[DocumentOut],
    status_code=status.HTTP_200_OK,
)
async def list_chat_documents(
    chat_id: int,
    current_user: User = Depends(get_current_user),
):
    chat = await asyncio.to_thread(
        ChatRepository.get_by_id,
        chat_id=chat_id,
        user_id=current_user.id,
    )

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or unauthorized.",
        )

    return await asyncio.to_thread(
        DocumentRepository.list_for_chat,
        chat_id=chat_id,
        user_id=current_user.id,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_200_OK,
)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
):
    document = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document_id,
        user_id=current_user.id,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or unauthorized.",
        )

    return document


@router.patch(
    "/{document_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_200_OK,
)
async def update_document(
    document_id: int,
    payload: DocumentMetadataUpdate,
    current_user: User = Depends(get_current_user),
):
    existing = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document_id,
        user_id=current_user.id,
    )

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or unauthorized.",
        )

    updated = await asyncio.to_thread(
        DocumentRepository.update_metadata,
        document_id=document_id,
        user_id=current_user.id,
        filename=payload.filename,
    )

    return updated


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
):
    document = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document_id,
        user_id=current_user.id,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or unauthorized.",
        )

    if document.storage_key:
        try:
            storage = get_storage_backend()
            await asyncio.to_thread(
                storage.delete,
                document.storage_key,
            )
        except Exception:
            logger.exception(
                "Physical storage deletion failed for document_id=%s",
                document_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document from storage.",
            )

    try:
        deleted = await asyncio.to_thread(
            DocumentRepository.delete,
            document_id=document_id,
            user_id=current_user.id,
        )
    except Exception as exc:
        logger.exception("Database deletion failed for document_id=%s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document from database.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document deletion failed.",
        )

    return None


@router.get(
    "/{document_id}/file",
    status_code=status.HTTP_200_OK,
)
async def get_document_file(
    document_id: int,
    current_user: User = Depends(get_current_user),
):
    document = await asyncio.to_thread(
        DocumentRepository.get_owned_document,
        document_id=document_id,
        user_id=current_user.id,
    )

    if not document or not document.storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        storage = get_storage_backend()
        stream = await asyncio.to_thread(
            storage.get_stream,
            document.storage_key,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    except Exception:
        logger.exception(
            "Unexpected error reading document storage document_id=%s",
            document_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document file.",
        )

    def stream_chunks():
        try:
            while chunk := stream.read(64 * 1024):
                yield chunk
        finally:
            if hasattr(stream, "close"):
                stream.close()

    filename = document.filename or f"document_{document.id}.pdf"
    encoded_filename = quote(filename)

    return StreamingResponse(
        stream_chunks(),
        media_type=document.mime_type or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{encoded_filename}"',
            "Cache-Control": "private, no-store",
        },
    )
