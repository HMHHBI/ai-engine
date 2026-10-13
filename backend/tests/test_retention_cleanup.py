from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from app.db.models import AuditEvent, Chat, Document, ResearchRun, ResearchRunDocument, User, Workspace
from app.services.retention_cleanup import cleanup_expired_records

def user(db: Session, email: str) -> User:
    row = User(name="Retention test", email=email, password="test-hash", is_active=True, token_version=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def workspace(db: Session, actor: User) -> Workspace:
    row = Workspace(name="Retention test", created_by=actor.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def run(db: Session, ws: Workspace, actor: User, state: str, at: datetime) -> ResearchRun:
    row = ResearchRun(
        workspace_id=ws.id,
        requester_id=actor.id,
        query="test query",
        status=state,
        answer={"answer": "kept"},
        run_metadata={},
        created_at=at,
        completed_at=None if state in {"queued", "running"} else at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def event(db: Session, actor: User, ws: Workspace, at: datetime) -> AuditEvent:
    row = AuditEvent(
        actor_id=actor.id,
        workspace_id=ws.id,
        action="test.event",
        resource_type="test",
        resource_id="1",
        outcome="success",
        metadata_payload={},
        created_at=at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def test_default_dry_run_deletes_nothing(db_session: Session):
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    old = now - timedelta(days=400)
    actor = user(db_session, "retention-dry@example.test")
    ws = workspace(db_session, actor)
    failed = run(db_session, ws, actor, "failed", old)
    audit = event(db_session, actor, ws, old)
    result = cleanup_expired_records(db_session, now=now)
    assert result.dry_run and result.failed_research_runs_eligible == 1
    assert result.failed_research_runs_deleted == 0 and result.audit_events_deleted == 0
    assert db_session.get(ResearchRun, failed.id) and db_session.get(AuditEvent, audit.id)

def test_only_old_failed_runs_without_provenance_are_deleted(db_session: Session):
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    old = now - timedelta(days=120)
    actor = user(db_session, "retention-status@example.test")
    ws = workspace(db_session, actor)
    failed = run(db_session, ws, actor, "failed", old)
    queued = run(db_session, ws, actor, "queued", old)
    running = run(db_session, ws, actor, "running", old)
    completed = run(db_session, ws, actor, "completed", old)
    recent = run(db_session, ws, actor, "failed", now - timedelta(days=5))
    result = cleanup_expired_records(db_session, dry_run=False, now=now, audit_retention_days=365)
    assert result.failed_research_runs_deleted == 1
    assert db_session.get(ResearchRun, failed.id) is None
    assert all(db_session.get(ResearchRun, x.id) is not None for x in (queued, running, completed, recent))

def test_failed_run_with_provenance_is_retained(db_session: Session):
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    old = now - timedelta(days=120)
    actor = user(db_session, "retention-prov@example.test")
    ws = workspace(db_session, actor)
    failed = run(db_session, ws, actor, "failed", old)
    chat = Chat(user_id=actor.id, title="source")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    doc = Document(user_id=actor.id, chat_id=chat.id, filename="source.pdf", mime_type="application/pdf", status="ready")
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    db_session.add(ResearchRunDocument(research_run_id=failed.id, document_id=doc.id, provenance={"filename": "source.pdf"}, created_at=old))
    db_session.commit()
    result = cleanup_expired_records(db_session, dry_run=False, now=now)
    assert result.failed_research_runs_deleted == 0
    assert db_session.get(ResearchRun, failed.id) is not None

def test_only_expired_audit_events_are_deleted(db_session: Session):
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    actor = user(db_session, "retention-audit@example.test")
    ws = workspace(db_session, actor)
    old = event(db_session, actor, ws, now - timedelta(days=400))
    recent = event(db_session, actor, ws, now - timedelta(days=5))
    result = cleanup_expired_records(db_session, dry_run=False, now=now)
    assert result.audit_events_deleted == 1
    assert db_session.get(AuditEvent, old.id) is None and db_session.get(AuditEvent, recent.id) is not None

@pytest.mark.parametrize("kwargs", [{"batch_size": 0}, {"batch_size": 10001}, {"failed_run_retention_days": 0}, {"audit_retention_days": 0}])
def test_invalid_limits_are_rejected(db_session: Session, kwargs):
    with pytest.raises(ValueError):
        cleanup_expired_records(db_session, **kwargs)

def test_batch_limit_applies_per_record_type(db_session: Session):
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    old = now - timedelta(days=500)
    actor = user(db_session, "retention-batch@example.test")
    ws = workspace(db_session, actor)
    runs = [run(db_session, ws, actor, "failed", old + timedelta(seconds=i)) for i in range(3)]
    events = [event(db_session, actor, ws, old + timedelta(seconds=i)) for i in range(3)]
    result = cleanup_expired_records(db_session, dry_run=False, batch_size=2, now=now)
    assert result.failed_research_runs_deleted == 2 and result.audit_events_deleted == 2
    assert sum(db_session.get(ResearchRun, x.id) is not None for x in runs) == 1
    assert sum(db_session.get(AuditEvent, x.id) is not None for x in events) == 1
