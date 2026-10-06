from __future__ import annotations

import asyncio
import io
import logging
import uuid
from typing import Any

from app.core.config import EmbeddingProvider
from app.db.session import session_scope
from app.repositories.document_job_repo import (
    DocumentJobRepository,
    DocumentJobTransitionError,
)
from app.repositories.document_repo import DocumentRepository
from app.services.document_ingestion_service import DocumentIngestionService
from app.utils.pdf_extractor import PDFExtractionError, PDFPage, extract_text_from_pdf
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)


class DocumentLifecycleService:
    """
    Coordinates the first-class document lifecycle.

    The Document row records the user-visible lifecycle stage while the
    existing DocumentJob row records durable execution state.

    User-visible lifecycle:
        uploading -> extracting -> indexing -> ready
                                      \
                                       -> failed

    DocumentJob lifecycle:
        queued -> processing -> ready
                              \
                               -> failed
    """

    @staticmethod
    def create_job(
        *,
        document_id: int,
        user_id: int,
    ):
        idempotency_key = (
            f"document:{document_id}:ingestion:{uuid.uuid4().hex}"
        )

        with session_scope() as db:
            repository = DocumentJobRepository(db)
            return repository.create(
                document_id=document_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )

    @staticmethod
    def claim_job(
        *,
        job_id: int,
        worker_id: str,
    ):
        with session_scope() as db:
            repository = DocumentJobRepository(db)
            return repository.transition_to_processing(
                job_id=job_id,
                worker_id=worker_id,
            )

    @staticmethod
    def mark_job_ready(job_id: int) -> None:
        with session_scope() as db:
            DocumentJobRepository(db).mark_ready(job_id)

    @staticmethod
    def mark_job_failed(
        job_id: int,
        error_message: str,
    ) -> None:
        with session_scope() as db:
            DocumentJobRepository(db).mark_failed(
                job_id,
                error_message,
            )

    @staticmethod
    def _read_storage(storage_key: str) -> bytes:
        storage = get_storage_backend()
        stream = storage.get_stream(storage_key)

        try:
            return stream.read()
        finally:
            if hasattr(stream, "close"):
                stream.close()

    @staticmethod
    def _extract_pages(
        *,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> list[PDFPage]:
        is_pdf = (
            mime_type.lower() == "application/pdf"
            or filename.lower().endswith(".pdf")
        )

        if is_pdf:
            try:
                return extract_text_from_pdf(content)
            except PDFExtractionError:
                raise

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Text document must be valid UTF-8.") from exc

        if not text.strip():
            raise ValueError("Document is empty or contains no readable text.")

        return [PDFPage(page_number=1, text=text)]

    @classmethod
    async def process_job(
        cls,
        *,
        document_id: int,
        user_id: int,
        job_id: int,
        embedding_provider: EmbeddingProvider,
        content: bytes | None = None,
        worker_id: str = "api-document-worker",
    ) -> dict[str, Any]:
        document = await asyncio.to_thread(
            DocumentRepository.get_owned_document,
            document_id=document_id,
            user_id=user_id,
        )

        if document is None:
            raise ValueError("Document not found or unauthorized.")

        if not document.storage_key:
            raise ValueError("Document has no durable storage object.")

        try:
            await asyncio.to_thread(
                cls.claim_job,
                job_id=job_id,
                worker_id=worker_id,
            )

            await asyncio.to_thread(
                DocumentRepository.update_status,
                document_id=document_id,
                user_id=user_id,
                status="extracting",
            )

            if content is None:
                content = await asyncio.to_thread(
                    cls._read_storage,
                    document.storage_key,
                )

            pages = await asyncio.to_thread(
                cls._extract_pages,
                content=content,
                filename=document.filename,
                mime_type=document.mime_type,
            )

            await asyncio.to_thread(
                DocumentRepository.update_metadata,
                document_id=document_id,
                user_id=user_id,
                page_count=len(pages),
            )

            await asyncio.to_thread(
                DocumentRepository.update_status,
                document_id=document_id,
                user_id=user_id,
                status="indexing",
            )

            result = await DocumentIngestionService.ingest(
                user_id=user_id,
                document_id=document_id,
                pages=pages,
                embedding_provider=embedding_provider,
            )

            await asyncio.to_thread(
                DocumentRepository.update_status,
                document_id=document_id,
                user_id=user_id,
                status="ready",
            )

            await asyncio.to_thread(
                cls.mark_job_ready,
                job_id,
            )

            return result

        except asyncio.CancelledError:
            await asyncio.to_thread(
                cls.mark_job_failed,
                job_id,
                "Document processing was cancelled.",
            )
            await asyncio.to_thread(
                DocumentRepository.update_status,
                document_id=document_id,
                user_id=user_id,
                status="failed",
                error_message="Document processing was cancelled.",
            )
            raise

        except Exception as exc:
            message = (
                str(exc).strip()
                or "Document ingestion failed."
            )

            logger.exception(
                "document_ingestion_failed",
                extra={
                    "event": "document_ingestion_failed",
                    "document_id": document_id,
                    "user_id": user_id,
                    "job_id": job_id,
                },
            )

            try:
                await asyncio.to_thread(
                    DocumentRepository.update_status,
                    document_id=document_id,
                    user_id=user_id,
                    status="failed",
                    error_message=message[:4000],
                )
            finally:
                await asyncio.to_thread(
                    cls.mark_job_failed,
                    job_id,
                    message,
                )

            raise
