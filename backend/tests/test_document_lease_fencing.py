import pytest
from app.db.models import DocumentJobStatus
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_job_repo import (
    DocumentJobOwnershipError,
    DocumentJobRepository,
)
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.services.document_lifecycle_service import DocumentLifecycleService


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

    # Worker A wakes up and attempts mark_ready with old lease
    with pytest.raises(DocumentJobOwnershipError):
        repo.transition_to_ready(job.id, worker_id="worker-A", attempt=1)

    # Worker A attempts mark_failed with old lease
    with pytest.raises(DocumentJobOwnershipError):
        repo.transition_to_failed(job.id, "Late failure", worker_id="worker-A", attempt=1)

    # Worker B successfully marks ready
    ready_job = repo.transition_to_ready(job.id, worker_id="worker-B", attempt=2)
    assert ready_job.status == DocumentJobStatus.READY.value


def test_stale_worker_atomic_transition_rejected(db_session):
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
    repo.transition_to_processing(job.id, "worker-A")

    # Requeue and Worker B claims
    repo.requeue_stale(job.id, "worker-A", attempt=1)
    repo.transition_to_processing(job.id, "worker-B")

    # Lifecycle atomic transition by stale Worker A
    with pytest.raises(DocumentJobOwnershipError):
        DocumentLifecycleService._atomic_transition(
            job_id=job.id,
            document_id=doc.id,
            user_id=user.id,
            worker_id="worker-A",
            attempt=1,
            document_status="ready",
            job_terminal_status="ready",
        )

    # Verify document status did not get overwritten to ready
    refreshed_doc = DocumentRepository.get_owned_document(doc.id, user.id)
    assert refreshed_doc.status != "ready"
