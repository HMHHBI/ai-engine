from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentJob, DocumentJobStatus

MAX_ERROR_MESSAGE_LENGTH = 4000


class DocumentJobTransitionError(ValueError):
    """Raised when an illegal document job state transition is requested."""
    pass


class DocumentJobOwnershipError(ValueError):
    """Raised when document and job ownership invariants are violated."""
    pass


class DocumentJobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        document_id: int,
        user_id: int,
        idempotency_key: str,
        max_attempts: int = 3,
    ) -> DocumentJob:
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")
        if doc.user_id != user_id:
            raise DocumentJobOwnershipError(
                f"Document {document_id} belongs to user {doc.user_id}, but job was requested for user {user_id}"
            )

        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        now = datetime.now(timezone.utc)
        job = DocumentJob(
            document_id=document_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            status=DocumentJobStatus.QUEUED.value,
            attempt=0,
            max_attempts=max_attempts,
            worker_id=None,
            queued_at=now,
            started_at=None,
            heartbeat_at=None,
            finished_at=None,
            cancel_requested_at=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: int) -> Optional[DocumentJob]:
        return self.db.query(DocumentJob).filter(DocumentJob.id == job_id).first()

    def get_owned_job(self, job_id: int, user_id: int) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id, DocumentJob.user_id == user_id)
            .first()
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(DocumentJob.idempotency_key == idempotency_key)
            .first()
        )

    def get_active_for_document(self, document_id: int) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(
                DocumentJob.document_id == document_id,
                DocumentJob.status.in_([DocumentJobStatus.QUEUED.value, DocumentJobStatus.PROCESSING.value]),
            )
            .first()
        )

    def count_active_for_user(self, user_id: int) -> int:
        return (
            self.db.query(func.count(DocumentJob.id))
            .filter(
                DocumentJob.user_id == user_id,
                DocumentJob.status.in_([DocumentJobStatus.QUEUED.value, DocumentJobStatus.PROCESSING.value]),
            )
            .scalar()
            or 0
        )

    def transition_to_processing(self, job_id: int, worker_id: str) -> DocumentJob:
        """
        Atomically claims a queued job for execution by locking the job row via SELECT FOR UPDATE.
        Guarantees that exactly one worker succeeds in transitioning a queued job to processing.
        """
        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id must be provided to transition to processing")

        # Atomic lock on the specific job row to eliminate check-then-update race conditions
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.QUEUED.value:
            raise DocumentJobTransitionError(
                f"Cannot transition job {job_id} from {job.status} to {DocumentJobStatus.PROCESSING.value}"
            )

        now = datetime.now(timezone.utc)
        job.status = DocumentJobStatus.PROCESSING.value
        job.attempt = job.attempt + 1
        job.worker_id = worker_id.strip()
        job.started_at = now
        job.heartbeat_at = now
        job.updated_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def update_heartbeat(self, job_id: int, worker_id: str) -> DocumentJob:
        job = self.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot update heartbeat for job {job_id} with status {job.status}"
            )

        if job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id} (owned by {job.worker_id})"
            )

        now = datetime.now(timezone.utc)
        job.heartbeat_at = now
        job.updated_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_ready(self, job_id: int) -> DocumentJob:
        job = self.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot mark job {job_id} as ready from status {job.status}"
            )

        now = datetime.now(timezone.utc)
        job.status = DocumentJobStatus.READY.value
        job.finished_at = now
        job.error_message = None
        job.worker_id = None
        job.heartbeat_at = None
        job.updated_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed(self, job_id: int, error_message: str) -> DocumentJob:
        job = self.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot mark job {job_id} as failed from status {job.status}"
            )

        clean_error = (error_message or "Unknown failure").strip()[:MAX_ERROR_MESSAGE_LENGTH]
        now = datetime.now(timezone.utc)
        job.status = DocumentJobStatus.FAILED.value
        job.finished_at = now
        job.error_message = clean_error
        job.worker_id = None
        job.heartbeat_at = None
        job.updated_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def request_cancellation(self, job_id: int, user_id: int) -> DocumentJob:
        """
        User/API control plane method: records cancellation intent.
        - If still queued (unclaimed), immediately transitions to cancelled.
        - If processing (claimed by worker), sets cancel_requested_at for worker to acknowledge.
        """
        job = self.get_owned_job(job_id, user_id)
        if not job:
            raise ValueError(f"Job {job_id} not found for user {user_id}")

        if job.status not in (DocumentJobStatus.QUEUED.value, DocumentJobStatus.PROCESSING.value):
            raise DocumentJobTransitionError(
                f"Cannot request cancellation for terminal job {job_id} with status {job.status}"
            )

        now = datetime.now(timezone.utc)
        job.cancel_requested_at = now
        job.updated_at = now

        if job.status == DocumentJobStatus.QUEUED.value:
            job.status = DocumentJobStatus.CANCELLED.value
            job.finished_at = now
            job.worker_id = None
            job.heartbeat_at = None
            job.error_message = None

        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_cancelled(self, job_id: int) -> DocumentJob:
        """
        Worker acknowledgement / internal transition method:
        Transitions a processing (or queued) job into the terminal CANCELLED state.
        """
        job = self.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in (DocumentJobStatus.QUEUED.value, DocumentJobStatus.PROCESSING.value):
            raise DocumentJobTransitionError(
                f"Cannot cancel terminal job {job_id} with status {job.status}"
            )

        now = datetime.now(timezone.utc)
        job.status = DocumentJobStatus.CANCELLED.value
        job.finished_at = now
        job.worker_id = None
        job.heartbeat_at = None
        job.error_message = None
        job.updated_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def get_latest_for_document(
        self,
        document_id: int,
        user_id: int,
    ) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(
                DocumentJob.document_id == document_id,
                DocumentJob.user_id == user_id,
            )
            .order_by(DocumentJob.id.desc())
            .first()
        )
