import pytest
from datetime import datetime, timezone, timedelta
from app.core.config import EmbeddingProvider
from app.db.models import DocumentJob, DocumentJobStatus
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_job_repo import (
    DocumentJobOwnershipError,
    DocumentJobRepository,
)
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.services.document_lifecycle_service import DocumentLifecycleService
from app.services.document_job_recovery import DocumentJobRecoveryService


def test_stale_worker_cannot_mark_job_ready(db_session):
    user = UserRepository.create(db_session, "Fence User 1", "fence1@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Chat")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test.pdf",
        mime_type="application/pdf",
        file_size=100,
        page_count=1,
        storage_key="storage_1",
    )

    repo = DocumentJobRepository(db_session)
    job = repo.create(doc.id, user.id, "idemp_fence_1")

    # Worker A claims attempt 1
    job_a = repo.transition_to_processing(job.id, "worker-A")
    assert job_a.attempt == 1
    assert job_a.worker_id == "worker-A"

    # Stale recovery requeues job
    repo.requeue_stale(job.id, "worker-A", attempt=1)

    # Worker B claims attempt 2
    job_b = repo.transition_to_processing(job.id, "worker-B")
    assert job_b.attempt == 2
    assert job_b.worker_id == "worker-B"

    # Worker A attempts mark_ready with old lease -> REJECTED
    with pytest.raises(DocumentJobOwnershipError):
        repo.transition_to_ready(job.id, worker_id="worker-A", attempt=1)

    # Worker A attempts mark_failed with old lease -> REJECTED
    with pytest.raises(DocumentJobOwnershipError):
        repo.transition_to_failed(job.id, "Late failure", worker_id="worker-A", attempt=1)

    # Worker B successfully marks ready
    ready_job = repo.transition_to_ready(job.id, worker_id="worker-B", attempt=2)
    assert ready_job.status == DocumentJobStatus.READY.value


@pytest.mark.asyncio
async def test_stale_worker_calling_process_job_cannot_modify_document_or_job(db_session):
    """
    Verifies that calling the REAL process_job() with a stale lease cannot overwrite
    either Document or DocumentJob state.
    """
    user = UserRepository.create(db_session, "Fence User 2", "fence2@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Chat 2")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test2.pdf",
        mime_type="application/pdf",
        file_size=100,
        page_count=1,
        storage_key="storage_2",
    )

    repo = DocumentJobRepository(db_session)
    job = repo.create(doc.id, user.id, "idemp_fence_2")
    
    # Worker A claims attempt 1
    repo.transition_to_processing(job.id, "worker-A")

    # Recovery requeues and Worker B claims attempt 2
    repo.requeue_stale(job.id, "worker-A", attempt=1)
    repo.transition_to_processing(job.id, "worker-B")

    # Worker A attempts to run process_job with attempt 1
    from types import SimpleNamespace
    fake_claimed_job = SimpleNamespace(id=job.id, attempt=1, worker_id="worker-A")

    with pytest.raises(DocumentJobOwnershipError):
        await DocumentLifecycleService.process_job(
            document_id=doc.id,
            user_id=user.id,
            job_id=job.id,
            embedding_provider=EmbeddingProvider.OLLAMA,
            content=b"Sample content",
            worker_id="worker-A",
            claimed_job=fake_claimed_job,
        )

    # Document must NOT be changed to ready or failed by Worker A
    refreshed_doc = DocumentRepository.get_owned_document(doc.id, user.id)
    assert refreshed_doc.status not in ("ready", "failed")

    # Job must still be owned by Worker B at attempt 2
    refreshed_job = repo.get_by_id(job.id)
    assert refreshed_job.worker_id == "worker-B"
    assert refreshed_job.attempt == 2


def test_recovery_race_against_concurrent_heartbeat(db_session):
    """
    If a worker refreshes its heartbeat while recovery inspects it,
    recovery must abort without modifying the job or document.
    """
    user = UserRepository.create(db_session, "Fence User 3", "fence3@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Chat 3")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test3.pdf",
        mime_type="application/pdf",
        file_size=100,
        page_count=1,
        storage_key="storage_3",
    )

    repo = DocumentJobRepository(db_session)
    job = repo.create(doc.id, user.id, "idemp_fence_3")
    repo.transition_to_processing(job.id, "worker-alive")

    # Simulate heartbeat refreshed just now
    repo.update_heartbeat(job.id, "worker-alive")

    recovery_service = DocumentJobRecoveryService()

    # Recovery attempts to recover alive job
    result = recovery_service.recover_stale_job(
        job_id=job.id,
        worker_id="worker-alive",
        attempt=1,
        stale_threshold_seconds=60.0,
    )

    # Must be skipped (returns None)
    assert result is None

    # Job must remain in PROCESSING
    refreshed_job = repo.get_by_id(job.id)
    assert refreshed_job.status == DocumentJobStatus.PROCESSING.value
    assert refreshed_job.worker_id == "worker-alive"


def test_fail_queued_dispatch_leaves_claimed_job_untouched(db_session):
    """
    If a worker already claimed a job, fail_queued_dispatch must not
    revert or overwrite the job/document to failed.
    """
    user = UserRepository.create(db_session, "Fence User 4", "fence4@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Chat 4")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test4.pdf",
        mime_type="application/pdf",
        file_size=100,
        page_count=1,
        storage_key="storage_4",
    )

    repo = DocumentJobRepository(db_session)
    job = repo.create(doc.id, user.id, "idemp_fence_4")
    repo.transition_to_processing(job.id, "worker-active")

    # Dispatch failure occurs after worker claimed
    DocumentLifecycleService.fail_queued_dispatch(
        document_id=doc.id,
        user_id=user.id,
        job_id=job.id,
        error_message="Redis error after claim",
    )

    # Job and doc must remain PROCESSING, NOT failed
    refreshed_job = repo.get_by_id(job.id)
    assert refreshed_job.status == DocumentJobStatus.PROCESSING.value
    assert refreshed_job.worker_id == "worker-active"


def test_transition_to_cancelled_clears_lease_and_updates_document(db_session):
    user = UserRepository.create(db_session, "Fence Cancel User 1", "fence_cancel1@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Cancel Chat 1")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test_cancel.pdf",
        mime_type="application/pdf",
        file_size=120,
        page_count=1,
        storage_key="storage_cancel",
    )
    job_repo = DocumentJobRepository(db_session)
    job = job_repo.create(doc.id, user.id, "idemp_fence_cancel_1")
    job = job_repo.transition_to_processing(job.id, "worker-cancel-1")
    initial_attempt = job.attempt

    DocumentLifecycleService._atomic_transition(
        job_id=job.id,
        document_id=doc.id,
        user_id=user.id,
        worker_id="worker-cancel-1",
        attempt=initial_attempt,
        document_status="cancelled",
        job_terminal_status="cancelled",
        error_message="Document processing was cancelled.",
    )

    db_session.expire_all()
    refreshed_job = job_repo.get_by_id(job.id)
    refreshed_doc = DocumentRepository.get_owned_document(doc.id, user.id)

    assert refreshed_job.status == DocumentJobStatus.CANCELLED.value
    assert refreshed_job.worker_id is None
    assert refreshed_job.heartbeat_at is None
    assert refreshed_job.finished_at is not None
    assert refreshed_doc.status == "cancelled"


def test_transition_to_cancelled_rejects_wrong_worker_and_stale_attempt(db_session):
    user = UserRepository.create(db_session, "Fence Cancel User 2", "fence_cancel2@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Cancel Chat 2")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test_cancel_fencing.pdf",
        mime_type="application/pdf",
        file_size=120,
        page_count=1,
        storage_key="storage_cancel_fencing",
    )
    job_repo = DocumentJobRepository(db_session)
    job = job_repo.create(doc.id, user.id, "idemp_fence_cancel_2")
    job = job_repo.transition_to_processing(job.id, "worker-owner")

    # Stale / wrong worker rejection
    with pytest.raises(DocumentJobOwnershipError):
        job_repo.transition_to_cancelled(
            job_id=job.id,
            worker_id="worker-imposter",
            attempt=job.attempt,
        )

    # Stale attempt rejection
    with pytest.raises(DocumentJobOwnershipError):
        job_repo.transition_to_cancelled(
            job_id=job.id,
            worker_id="worker-owner",
            attempt=job.attempt + 1,
        )

    # State untouched
    refreshed = job_repo.get_by_id(job.id)
    assert refreshed.status == DocumentJobStatus.PROCESSING.value
    assert refreshed.worker_id == "worker-owner"


def test_transition_to_cancelled_cannot_overwrite_ready_job(db_session):
    from app.repositories.document_job_repo import DocumentJobTransitionError

    user = UserRepository.create(db_session, "Fence Cancel User 3", "fence_cancel3@example.com", "Password!123")
    chat = ChatRepository.create_chat(user.id, "Fence Cancel Chat 3")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="test_cancel_ready.pdf",
        mime_type="application/pdf",
        file_size=120,
        page_count=1,
        storage_key="storage_cancel_ready",
    )
    job_repo = DocumentJobRepository(db_session)
    job = job_repo.create(doc.id, user.id, "idemp_fence_cancel_3")
    job = job_repo.transition_to_processing(job.id, "worker-ready")
    job_repo.transition_to_ready(job.id, worker_id="worker-ready", attempt=job.attempt)

    with pytest.raises(DocumentJobTransitionError):
        job_repo.transition_to_cancelled(
            job_id=job.id,
            worker_id="worker-ready",
            attempt=job.attempt,
        )

    refreshed = job_repo.get_by_id(job.id)
    assert refreshed.status == DocumentJobStatus.READY.value
