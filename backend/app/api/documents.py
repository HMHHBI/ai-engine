from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.db.models import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.document_schema import DocumentMetadataUpdate, DocumentOut
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
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
    """
    List all documents associated with a chat owned by the current user.
    """
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

    documents = await asyncio.to_thread(
        DocumentRepository.list_for_chat,
        chat_id=chat_id,
        user_id=current_user.id,
    )
    return documents


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_200_OK,
)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Get metadata for a specific document with dual ownership verification.
    """
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
    """
    Update document metadata (e.g. filename, file_size, page_count) with dual ownership verification.
    """
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
        file_size=payload.file_size,
        page_count=payload.page_count,
        storage_url=payload.storage_url,
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
    """
    Delete a document with storage-first orchestration.
    Physical storage must succeed before DB removal to prevent orphaned objects.
    """
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

    # 1. Physical storage deletion first
    if document.storage_key:
        try:
            storage = get_storage_backend()
            await asyncio.to_thread(storage.delete, document.storage_key)
        except Exception:
            logger.exception(
                "Physical storage deletion failed for document_id=%s storage_key=%s",
                document_id,
                document.storage_key,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document from storage.",
            )

    # 2. Vector chunks explicit cleanup
    await asyncio.to_thread(
        VectorRepository.delete_document_chunks,
        user_id=current_user.id,
        document_id=document_id,
    )

    # 3. Database deletion (cascades chunks if any remain)
    deleted = await asyncio.to_thread(
        DocumentRepository.delete,
        document_id=document_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document deletion failed.",
        )
    return None
