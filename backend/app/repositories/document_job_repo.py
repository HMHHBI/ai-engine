from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentJob, DocumentJobStatus

MAX_ERROR_MESSAGE_LENGTH = 4000


class DocumentJobTransitionError(ValueError):
    """Raised when an illegal document job state transition is requested."""


class DocumentJobOwnershipError(ValueError):
    """Raised when document and job ownership invariants are violated."""


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
        doc = (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        if doc.user_id != user_id:
            raise DocumentJobOwnershipError(
                f"Document {document_id} belongs to user {doc.user_id}, "
                f"but job was requested for user {user_id}"
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
            finished_at=None,
            heartbeat_at=None,
            error_message=None,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_owned_job(self, job_id: int, user_id: int) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id, DocumentJob.user_id == user_id)
            .first()
        )

    def get_by_id(self, job_id: int) -> Optional[DocumentJob]:
        return self.db.query(DocumentJob).filter(DocumentJob.id == job_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(DocumentJob.idempotency_key == idempotency_key)
            .first()
        )

    def get_latest_for_document(
        self,
        document_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[DocumentJob]:
        query = self.db.query(DocumentJob).filter(DocumentJob.document_id == document_id)
        if user_id is not None:
            query = query.filter(DocumentJob.user_id == user_id)
        return query.order_by(DocumentJob.created_at.desc(), DocumentJob.id.desc()).first()

    def get_active_jobs_for_user(self, user_id: int) -> list[DocumentJob]:
        return (
            self.db.query(DocumentJob)
            .filter(
                DocumentJob.user_id == user_id,
                DocumentJob.status.in_([
                    DocumentJobStatus.QUEUED.value,
                    DocumentJobStatus.PROCESSING.value,
                ]),
            )
            .order_by(DocumentJob.created_at.asc())
            .all()
        )

    def count_active_for_user(self, user_id: int) -> int:
        return (
            self.db.query(DocumentJob)
            .filter(
                DocumentJob.user_id == user_id,
                DocumentJob.status.in_([
                    DocumentJobStatus.QUEUED.value,
                    DocumentJobStatus.PROCESSING.value,
                ]),
            )
            .count()
        )

    def count_by_status(self, user_id: Optional[int] = None) -> dict[str, int]:
        query = self.db.query(
            DocumentJob.status,
            func.count(DocumentJob.id),
        )
        if user_id is not None:
            query = query.filter(DocumentJob.user_id == user_id)
        counts = query.group_by(DocumentJob.status).all()
        return {status: count for status, count in counts}

    def transition_to_processing(self, job_id: int, worker_id: str) -> DocumentJob:
        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id must be provided to transition to processing")

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
                f"Cannot transition job {job_id} to PROCESSING from {job.status}"
            )

        now = datetime.now(timezone.utc)
        job.status = DocumentJobStatus.PROCESSING.value
        job.worker_id = worker_id.strip()
        job.attempt += 1
        job.started_at = now
        job.heartbeat_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def update_heartbeat(self, job_id: int, worker_id: str) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot heartbeat job {job_id} with status {job.status}"
            )

        if job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id} (owned by {job.worker_id})"
            )

        job.heartbeat_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def request_cancellation(self, job_id: int, user_id: int) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.user_id != user_id:
            raise DocumentJobOwnershipError(
                f"User {user_id} does not own job {job_id}"
            )

        if job.status in (
            DocumentJobStatus.READY.value,
            DocumentJobStatus.FAILED.value,
            DocumentJobStatus.CANCELLED.value,
        ):
            raise DocumentJobTransitionError(
                f"Cannot request cancellation for job {job_id} in terminal state {job.status}"
            )

        if job.status == DocumentJobStatus.PROCESSING.value:
            job.cancel_requested_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            return job

        job.status = DocumentJobStatus.CANCELLED.value
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def is_cancel_requested(self, job_id: int, worker_id: Optional[str] = None) -> bool:
        job = self.get_by_id(job_id)
        if not job:
            return False

        if worker_id is not None and job.worker_id not in (worker_id, None):
            return False

        if job.status == DocumentJobStatus.CANCELLED.value:
            return True

        return (
            job.status == DocumentJobStatus.PROCESSING.value
            and job.cancel_requested_at is not None
        )

    def transition_to_ready(
        self,
        job_id: int,
        worker_id: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status == DocumentJobStatus.READY.value:
            return job

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot transition job {job_id} to READY from {job.status}"
            )

        if worker_id is not None and job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id} (owned by {job.worker_id})"
            )

        if attempt is not None and job.attempt != attempt:
            raise DocumentJobOwnershipError(
                f"Attempt {attempt} does not match current attempt {job.attempt} on job {job_id}"
            )

        job.status = DocumentJobStatus.READY.value
        job.worker_id = None
        job.heartbeat_at = None
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_ready(
        self,
        job_id: int,
        worker_id: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> DocumentJob:
        return self.transition_to_ready(job_id=job_id, worker_id=worker_id, attempt=attempt)

    def transition_to_failed(
        self,
        job_id: int,
        error_message: str,
        worker_id: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")


        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot transition job {job_id} to FAILED from {job.status}; must be PROCESSING"
            )

        if worker_id is not None and job.worker_id is not None and job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id} (owned by {job.worker_id})"
            )

        if attempt is not None and job.attempt != attempt:
            raise DocumentJobOwnershipError(
                f"Attempt {attempt} does not match current attempt {job.attempt} on job {job_id}"
            )

        truncated_message = (error_message or "").strip()[:MAX_ERROR_MESSAGE_LENGTH]
        job.status = DocumentJobStatus.FAILED.value
        job.worker_id = None
        job.heartbeat_at = None
        job.error_message = truncated_message or None
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed(
        self,
        job_id: int,
        error_message: str,
        worker_id: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> DocumentJob:
        return self.transition_to_failed(
            job_id=job_id,
            error_message=error_message,
            worker_id=worker_id,
            attempt=attempt,
        )

    def transition_to_cancelled(
        self,
        job_id: int,
        worker_id: Optional[str] = None,
        attempt: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status == DocumentJobStatus.CANCELLED.value:
            return job

        if job.status not in (
            DocumentJobStatus.QUEUED.value,
            DocumentJobStatus.PROCESSING.value,
        ):
            raise DocumentJobTransitionError(
                f"Cannot transition job {job_id} to CANCELLED from {job.status}"
            )

        if worker_id is not None and job.worker_id is not None and job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id} (owned by {job.worker_id})"
            )

        if attempt is not None and job.attempt != attempt:
            raise DocumentJobOwnershipError(
                f"Attempt {attempt} does not match current attempt {job.attempt} on job {job_id}"
            )

        job.status = DocumentJobStatus.CANCELLED.value
        job.worker_id = None
        job.heartbeat_at = None
        if error_message:
            job.error_message = (error_message or "").strip()[:MAX_ERROR_MESSAGE_LENGTH]
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_cancelled(
        self,
        job_id: int,
        worker_id: Optional[str] = None,
    ) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in (
            DocumentJobStatus.QUEUED.value,
            DocumentJobStatus.PROCESSING.value,
        ):
            raise DocumentJobTransitionError(
                f"Cannot transition job {job_id} to CANCELLED from {job.status}"
            )

        if worker_id is not None and job.worker_id != worker_id:
            raise DocumentJobOwnershipError(
                f"Worker {worker_id} does not own active lease on job {job_id}"
            )

        job.status = DocumentJobStatus.CANCELLED.value
        job.worker_id = None
        job.heartbeat_at = None
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def requeue_stale(
        self,
        job_id: int,
        worker_id: str,
        attempt: int,
    ) -> DocumentJob:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != DocumentJobStatus.PROCESSING.value:
            raise DocumentJobTransitionError(
                f"Cannot requeue job {job_id} from {job.status}; must be PROCESSING"
            )

        if job.worker_id != worker_id or job.attempt != attempt:
            raise DocumentJobOwnershipError(
                f"Cannot requeue job {job_id}: expected worker {worker_id} attempt {attempt}, got {job.worker_id} / {job.attempt}"
            )

        job.status = DocumentJobStatus.QUEUED.value
        job.worker_id = None
        job.started_at = None
        job.heartbeat_at = None
        job.queued_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def fail_queued(
        self,
        job_id: int,
        error_message: str,
    ) -> Optional[DocumentJob]:
        job = (
            self.db.query(DocumentJob)
            .filter(DocumentJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            return None

        if job.status != DocumentJobStatus.QUEUED.value:
            return job

        job.status = DocumentJobStatus.FAILED.value
        job.error_message = (error_message or "").strip()[:MAX_ERROR_MESSAGE_LENGTH]
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job
