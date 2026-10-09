from __future__ import annotations
from app.repositories.document_repo import DocumentRepository

import asyncio
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import EmbeddingProvider
from app.db.models import Document, DocumentJob, DocumentJobStatus
from app.db.session import session_scope
from app.repositories.document_job_repo import (
    DocumentJobOwnershipError,
    DocumentJobRepository,
    DocumentJobTransitionError,
)
from app.services.document_ingestion_service import DocumentIngestionService
from app.storage import get_storage_backend
from app.utils.pdf_extractor import (
    PDFExtractionError,
    PDFPage,
    extract_text_from_pdf,
)

logger = logging.getLogger(__name__)


class DocumentLifecycleService:
    @staticmethod
    def create_job(
        *,
        document_id: int,
        user_id: int,
    ):
        idempotency_key = f"document:{document_id}:ingestion:{uuid.uuid4().hex}"
        with session_scope() as db:
            repo = DocumentJobRepository(db)
            return repo.create(
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
            repo = DocumentJobRepository(db)
            return repo.transition_to_processing(
                job_id=job_id,
                worker_id=worker_id,
            )

    @staticmethod
    def is_cancel_requested(
        *,
        job_id: int,
        worker_id: str,
    ) -> bool:
        with session_scope() as db:
            repo = DocumentJobRepository(db)
            return repo.is_cancel_requested(job_id=job_id, worker_id=worker_id)

    @classmethod
    def fail_queued_dispatch(
        cls,
        *,
        document_id: int,
        user_id: int,
        job_id: int,
        error_message: str,
    ) -> None:
        """
        Atomically mark still-queued job and document as failed if enqueue fails.
        Executes within a single transaction under row lock.
        Leaves state completely untouched if worker has already claimed it.
        """
        with session_scope() as db:
            job = (
                db.query(DocumentJob)
                .filter(DocumentJob.id == job_id)
                .with_for_update()
                .first()
            )
            if not job or job.status != DocumentJobStatus.QUEUED.value:
                return

            job.status = DocumentJobStatus.FAILED.value
            job.error_message = (error_message or "").strip()[:4000]
            job.finished_at = datetime.now(timezone.utc)
            job.worker_id = None
            job.heartbeat_at = None

            doc = (
                db.query(Document)
                .filter(Document.id == document_id, Document.user_id == user_id)
                .with_for_update()
                .first()
            )
            if doc:
                doc.status = document_status
                if error_message is not None:
                    doc.error_message = error_message[:4000]
                if page_count is not None:
                    doc.page_count = page_count

            if job_terminal_status == "ready":
                job.status = DocumentJobStatus.READY.value
                job.worker_id = None
                job.heartbeat_at = None
                job.finished_at = datetime.now(timezone.utc)
            elif job_terminal_status == "failed":
                job.status = DocumentJobStatus.FAILED.value
                job.worker_id = None
                job.heartbeat_at = None
                job.error_message = (error_message or "")[:4000]
                job.finished_at = datetime.now(timezone.utc)
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
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> list[PDFPage]:
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            try:
                return extract_text_from_pdf(file_bytes)
            except PDFExtractionError:
                raise
            except Exception as e:
                raise PDFExtractionError(f"Unexpected extraction failure: {e}") from e

        text = file_bytes.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError("Document is empty or contains no readable text.")
        return [PDFPage(page_number=1, text=text)]

    @classmethod
    def _atomic_transition(
        cls,
        *,
        job_id: int,
        document_id: int,
        user_id: int,
        worker_id: str,
        attempt: int,
        document_status: str,
        job_terminal_status: Optional[str] = None,
        error_message: Optional[str] = None,
        page_count: Optional[int] = None,
    ) -> None:
        with session_scope() as db:
            job_repo = DocumentJobRepository(db)
            job = (
                db.query(DocumentJob)
                .filter(DocumentJob.id == job_id)
                .with_for_update()
                .first()
            )
            if not job:
                raise DocumentJobOwnershipError(f"Job {job_id} not found.")

            if job.worker_id != worker_id or job.attempt != attempt:
                raise DocumentJobOwnershipError(
                    f"Fencing conflict: Job {job_id} is owned by worker '{job.worker_id}' at attempt {job.attempt}, "
                    f"rejecting update from worker '{worker_id}' at attempt {attempt}."
                )

            doc = (
                db.query(Document)
                .filter(Document.id == document_id, Document.user_id == user_id)
                .with_for_update()
                .first()
            )
            if doc:
                doc.status = document_status
                if error_message is not None:
                    doc.error_message = error_message[:4000]
                if page_count is not None:
                    doc.page_count = page_count

            if job_terminal_status == "ready":
                job_repo.transition_to_ready(job_id=job_id, worker_id=worker_id, attempt=attempt)
            elif job_terminal_status == "failed":
                job_repo.transition_to_failed(
                    job_id=job_id,
                    error_message=error_message or "Job failed",
                    worker_id=worker_id,
                    attempt=attempt,
                )

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
        claimed_job: Any = None,
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

        if claimed_job is None:
            claimed_job = await asyncio.to_thread(
                cls.claim_job,
                job_id=job_id,
                worker_id=worker_id,
            )
        attempt = claimed_job.attempt

        try:
            # 1. Transition to extracting (strictly atomic, fenced)
            await asyncio.to_thread(
                cls._atomic_transition,
                job_id=job_id,
                document_id=document_id,
                user_id=user_id,
                worker_id=worker_id,
                attempt=attempt,
                document_status="extracting",
            )

            if content is None:
                content = await asyncio.to_thread(
                    cls._read_storage,
                    document.storage_key,
                )

            pages = await asyncio.to_thread(
                cls._extract_pages,
                file_bytes=content,
                filename=document.filename,
                mime_type=document.mime_type,
            )

            # 2. Transition to indexing (strictly atomic, fenced)
            await asyncio.to_thread(
                cls._atomic_transition,
                job_id=job_id,
                document_id=document_id,
                user_id=user_id,
                worker_id=worker_id,
                attempt=attempt,
                document_status="indexing",
                page_count=len(pages),
            )

            # 3. Vector Ingestion
            result = await DocumentIngestionService.ingest(
                user_id=user_id,
                document_id=document_id,
                pages=pages,
                embedding_provider=embedding_provider,
            )

            # 4. Atomic terminal READY (fenced)
            await asyncio.to_thread(
                cls._atomic_transition,
                job_id=job_id,
                document_id=document_id,
                user_id=user_id,
                worker_id=worker_id,
                attempt=attempt,
                document_status="ready",
                job_terminal_status="ready",
            )

            return result

        except asyncio.CancelledError:
            await asyncio.to_thread(
                cls._atomic_transition,
                job_id=job_id,
                document_id=document_id,
                user_id=user_id,
                worker_id=worker_id,
                attempt=attempt,
                document_status="failed",
                job_terminal_status="failed",
                error_message="Document processing was cancelled.",
            )
            raise

        except Exception as exc:
            message = str(exc).strip() or "Document ingestion failed."
            logger.exception(
                "document_ingestion_failed",
                extra={
                    "event": "document_ingestion_failed",
                    "document_id": document_id,
                    "user_id": user_id,
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "attempt": attempt,
                },
            )
            try:
                await asyncio.to_thread(
                    cls._atomic_transition,
                    job_id=job_id,
                    document_id=document_id,
                    user_id=user_id,
                    worker_id=worker_id,
                    attempt=attempt,
                    document_status="failed",
                    job_terminal_status="failed",
                    error_message=message[:4000],
                )
            except DocumentJobOwnershipError:
                logger.warning(
                    f"Stale worker {worker_id} suppressed from writing failed terminal state for job {job_id}"
                )
            raise
