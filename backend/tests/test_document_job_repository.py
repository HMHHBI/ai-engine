import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Chat,
    Document,
    DocumentJob,
    DocumentJobStatus,
    User,
)
from app.repositories.document_job_repo import (
    DocumentJobOwnershipError,
    DocumentJobRepository,
    DocumentJobTransitionError,
    MAX_ERROR_MESSAGE_LENGTH,
)


@pytest.fixture
def test_users(db_session: Session):
    u1 = User(
        name="User One",
        email="job_user1@example.com",
        password="hashedpassword123",
    )
    u2 = User(
        name="User Two",
        email="job_user2@example.com",
        password="hashedpassword123",
    )
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)
    return u1, u2


@pytest.fixture
def test_documents(db_session: Session, test_users):
    u1, u2 = test_users
    c1 = Chat(user_id=u1.id, title="Chat 1")
    c2 = Chat(user_id=u2.id, title="Chat 2")
    db_session.add_all([c1, c2])
    db_session.commit()

    d1 = Document(
        user_id=u1.id,
        chat_id=c1.id,
        filename="doc1.pdf",
        mime_type="application/pdf",
        storage_key="docs/u1/doc1.pdf",
    )
    d2 = Document(
        user_id=u2.id,
        chat_id=c2.id,
        filename="doc2.pdf",
        mime_type="application/pdf",
        storage_key="docs/u2/doc2.pdf",
    )
    db_session.add_all([d1, d2])
    db_session.commit()
    db_session.refresh(d1)
    db_session.refresh(d2)
    return d1, d2


def test_job_creation_and_defaults(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:1",
    )

    assert job.id is not None
    assert job.status == DocumentJobStatus.QUEUED.value
    assert job.attempt == 0
    assert job.max_attempts == 3
    assert job.worker_id is None
    assert job.queued_at is not None
    assert job.started_at is None
    assert job.heartbeat_at is None
    assert job.finished_at is None
    assert job.error_message is None


def test_cross_user_document_creation_rejected(db_session: Session, test_users, test_documents):
    _, u2 = test_users
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    # d1 belongs to u1, attempting to create with u2 must fail
    with pytest.raises(DocumentJobOwnershipError):
        repo.create(
            document_id=d1.id,
            user_id=u2.id,
            idempotency_key=f"document:{d1.id}:illegal:1",
        )


def test_database_enforces_one_active_job_per_document(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:1",
    )

    # Second active job creation should violate partial unique index
    with pytest.raises(IntegrityError):
        repo.create(
            document_id=d1.id,
            user_id=d1.user_id,
            idempotency_key=f"document:{d1.id}:ingestion:2",
        )
    db_session.rollback()


def test_state_transition_lifecycle_success(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:success",
    )

    # Claim for processing
    job = repo.transition_to_processing(job.id, worker_id="worker-node-1")
    assert job.status == DocumentJobStatus.PROCESSING.value
    assert job.attempt == 1
    assert job.worker_id == "worker-node-1"
    assert job.started_at is not None
    assert job.heartbeat_at is not None

    # Heartbeat update
    job = repo.update_heartbeat(job.id, worker_id="worker-node-1")
    assert job.heartbeat_at is not None

    # Complete job successfully
    job = repo.mark_ready(job.id)
    assert job.status == DocumentJobStatus.READY.value
    assert job.worker_id is None
    assert job.heartbeat_at is None
    assert job.finished_at is not None
    assert job.error_message is None

    # After completion (terminal), a new active job can be created for the document
    job2 = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:reindex",
    )
    assert job2.status == DocumentJobStatus.QUEUED.value


def test_state_transition_lifecycle_failure(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:fail",
    )

    repo.transition_to_processing(job.id, worker_id="worker-node-2")
    long_error = "Extraction failure: " + ("x" * 5000)
    failed_job = repo.mark_failed(job.id, error_message=long_error)

    assert failed_job.status == DocumentJobStatus.FAILED.value
    assert failed_job.worker_id is None
    assert failed_job.heartbeat_at is None
    assert failed_job.finished_at is not None
    assert len(failed_job.error_message) <= MAX_ERROR_MESSAGE_LENGTH


def test_cancellation_workflow(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    # 1. Queued job cancel immediately cancels
    job1 = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:cancel_q",
    )
    cancelled1 = repo.request_cancellation(job1.id, user_id=d1.user_id)
    assert cancelled1.status == DocumentJobStatus.CANCELLED.value
    assert cancelled1.finished_at is not None

    # 2. Processing job records cancel intent then marks cancelled
    job2 = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:cancel_p",
    )
    repo.transition_to_processing(job2.id, worker_id="worker-node-3")
    proc_cancel_req = repo.request_cancellation(job2.id, user_id=d1.user_id)
    assert proc_cancel_req.status == DocumentJobStatus.PROCESSING.value
    assert proc_cancel_req.cancel_requested_at is not None

    cancelled2 = repo.mark_cancelled(job2.id)
    assert cancelled2.status == DocumentJobStatus.CANCELLED.value
    assert cancelled2.finished_at is not None
    assert cancelled2.worker_id is None


def test_invalid_transitions_are_blocked(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:invalids",
    )

    # Cannot mark ready or failed directly from QUEUED
    with pytest.raises(DocumentJobTransitionError):
        repo.mark_ready(job.id)
    with pytest.raises(DocumentJobTransitionError):
        repo.mark_failed(job.id, "fail")

    # Transition to PROCESSING
    repo.transition_to_processing(job.id, worker_id="worker-1")

    # Cannot transition to PROCESSING again
    with pytest.raises(DocumentJobTransitionError):
        repo.transition_to_processing(job.id, worker_id="worker-2")

    # Complete
    repo.mark_ready(job.id)

    # Terminal job cannot transition to processing or be cancelled
    with pytest.raises(DocumentJobTransitionError):
        repo.transition_to_processing(job.id, worker_id="worker-1")
    with pytest.raises(DocumentJobTransitionError):
        repo.request_cancellation(job.id, user_id=d1.user_id)
    with pytest.raises(DocumentJobTransitionError):
        repo.mark_cancelled(job.id)


def test_ownership_and_counting_queries(db_session: Session, test_users, test_documents):
    u1, u2 = test_users
    d1, d2 = test_documents
    repo = DocumentJobRepository(db_session)

    j1 = repo.create(
        document_id=d1.id,
        user_id=u1.id,
        idempotency_key=f"document:{d1.id}:owned:1",
    )

    # u2 cannot retrieve u1's job via get_owned_job
    assert repo.get_owned_job(j1.id, user_id=u2.id) is None
    assert repo.get_owned_job(j1.id, user_id=u1.id) is not None

    # Active count per user
    assert repo.count_active_for_user(u1.id) == 1
    assert repo.count_active_for_user(u2.id) == 0

    j2 = repo.create(
        document_id=d2.id,
        user_id=u2.id,
        idempotency_key=f"document:{d2.id}:owned:2",
    )
    assert repo.count_active_for_user(u2.id) == 1

    # Completing j1 decrements active count
    repo.transition_to_processing(j1.id, worker_id="worker-1")
    repo.mark_ready(j1.id)
    assert repo.count_active_for_user(u1.id) == 0


def test_cascade_deletion(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:cascade:1",
    )
    job_id = job.id

    # Delete the parent document
    db_session.delete(d1)
    db_session.commit()

    # DocumentJob must cascade delete
    assert repo.get_by_id(job_id) is None
