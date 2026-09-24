import concurrent.futures
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Chat,
    Document,
    DocumentJob,
    DocumentJobStatus,
    User,
)
from app.db.session import SessionLocal
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

    with pytest.raises(IntegrityError):
        repo.create(
            document_id=d1.id,
            user_id=d1.user_id,
            idempotency_key=f"document:{d1.id}:ingestion:2",
        )
    db_session.rollback()


def test_database_enforces_status_check_constraint(db_session: Session, test_documents):
    d1, _ = test_documents
    # Directly attempt to insert an invalid status value into the table
    stmt = text(
        """
        INSERT INTO document_jobs (document_id, user_id, status, attempt, max_attempts, idempotency_key, queued_at, created_at, updated_at)
        VALUES (:doc_id, :user_id, 'banana', 0, 3, 'invalid-status-key', now(), now(), now())
        """
    )
    with pytest.raises(IntegrityError) as exc_info:
        db_session.execute(stmt, {"doc_id": d1.id, "user_id": d1.user_id})
        db_session.commit()
    assert "ck_document_jobs_valid_status" in str(exc_info.value)
    db_session.rollback()


def test_database_enforces_attempt_check_constraints(db_session: Session, test_documents):
    d1, _ = test_documents
    # 1. Negative attempt
    stmt_neg = text(
        """
        INSERT INTO document_jobs (document_id, user_id, status, attempt, max_attempts, idempotency_key, queued_at, created_at, updated_at)
        VALUES (:doc_id, :user_id, 'queued', -1, 3, 'neg-attempt-key', now(), now(), now())
        """
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(stmt_neg, {"doc_id": d1.id, "user_id": d1.user_id})
        db_session.commit()
    assert "ck_document_jobs_attempt_non_negative" in str(exc.value)
    db_session.rollback()

    # 2. Zero max_attempts
    stmt_zero_max = text(
        """
        INSERT INTO document_jobs (document_id, user_id, status, attempt, max_attempts, idempotency_key, queued_at, created_at, updated_at)
        VALUES (:doc_id, :user_id, 'queued', 0, 0, 'zero-max-key', now(), now(), now())
        """
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(stmt_zero_max, {"doc_id": d1.id, "user_id": d1.user_id})
        db_session.commit()
    assert "ck_document_jobs_max_attempts_positive" in str(exc.value)
    db_session.rollback()

    # 3. attempt > max_attempts
    stmt_exceed = text(
        """
        INSERT INTO document_jobs (document_id, user_id, status, attempt, max_attempts, idempotency_key, queued_at, created_at, updated_at)
        VALUES (:doc_id, :user_id, 'queued', 4, 3, 'exceed-key', now(), now(), now())
        """
    )
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(stmt_exceed, {"doc_id": d1.id, "user_id": d1.user_id})
        db_session.commit()
    assert "ck_document_jobs_attempt_lte_max" in str(exc.value)
    db_session.rollback()


def test_concurrent_workers_claim_exactly_once(test_documents):
    """
    Validates that two concurrent workers using separate DB sessions attempting
    to claim the same queued job will serialize via SELECT FOR UPDATE, resulting
    in exactly one successful claim and one transition error.
    """
    d1, _ = test_documents

    # Create job in an isolated session
    setup_db = SessionLocal()
    repo = DocumentJobRepository(setup_db)
    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:concurrency:claim",
    )
    job_id = job.id
    setup_db.close()

    results = []

    def claim_job(worker_name: str):
        thread_db = SessionLocal()
        try:
            r = DocumentJobRepository(thread_db)
            claimed = r.transition_to_processing(job_id=job_id, worker_id=worker_name)
            return ("SUCCESS", worker_name, claimed.attempt)
        except DocumentJobTransitionError as e:
            return ("REJECTED", worker_name, str(e))
        except Exception as e:
            return ("ERROR", worker_name, str(e))
        finally:
            thread_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(claim_job, "worker-alpha")
        f2 = executor.submit(claim_job, "worker-beta")
        results = [f1.result(), f2.result()]

    statuses = [r[0] for r in results]
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("REJECTED") == 1

    # Verify final state in DB
    verify_db = SessionLocal()
    final_job = DocumentJobRepository(verify_db).get_by_id(job_id)
    assert final_job.status == DocumentJobStatus.PROCESSING.value
    assert final_job.attempt == 1
    assert final_job.worker_id in ["worker-alpha", "worker-beta"]
    verify_db.close()


def test_state_transition_lifecycle_success(db_session: Session, test_documents):
    d1, _ = test_documents
    repo = DocumentJobRepository(db_session)

    job = repo.create(
        document_id=d1.id,
        user_id=d1.user_id,
        idempotency_key=f"document:{d1.id}:ingestion:success",
    )

    job = repo.transition_to_processing(job.id, worker_id="worker-node-1")
    assert job.status == DocumentJobStatus.PROCESSING.value
    assert job.attempt == 1
    assert job.worker_id == "worker-node-1"
    assert job.started_at is not None
    assert job.heartbeat_at is not None

    job = repo.update_heartbeat(job.id, worker_id="worker-node-1")
    assert job.heartbeat_at is not None

    job = repo.mark_ready(job.id)
    assert job.status == DocumentJobStatus.READY.value
    assert job.worker_id is None
    assert job.heartbeat_at is None
    assert job.finished_at is not None
    assert job.error_message is None

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

    with pytest.raises(DocumentJobTransitionError):
        repo.mark_ready(job.id)
    with pytest.raises(DocumentJobTransitionError):
        repo.mark_failed(job.id, "fail")

    repo.transition_to_processing(job.id, worker_id="worker-1")

    with pytest.raises(DocumentJobTransitionError):
        repo.transition_to_processing(job.id, worker_id="worker-2")

    repo.mark_ready(job.id)

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

    assert repo.get_owned_job(j1.id, user_id=u2.id) is None
    assert repo.get_owned_job(j1.id, user_id=u1.id) is not None

    assert repo.count_active_for_user(u1.id) == 1
    assert repo.count_active_for_user(u2.id) == 0

    j2 = repo.create(
        document_id=d2.id,
        user_id=u2.id,
        idempotency_key=f"document:{d2.id}:owned:2",
    )
    assert repo.count_active_for_user(u2.id) == 1

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

    db_session.delete(d1)
    db_session.commit()

    assert repo.get_by_id(job_id) is None
