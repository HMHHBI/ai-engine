from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.db.models import AuditEvent, ResearchRun

@dataclass(frozen=True)
class RetentionCleanupResult:
    dry_run: bool
    failed_research_runs_eligible: int
    failed_research_runs_deleted: int
    audit_events_eligible: int
    audit_events_deleted: int

def cleanup_expired_records(
    db: Session,
    *,
    dry_run: bool = True,
    batch_size: int = 100,
    failed_run_retention_days: int = 90,
    audit_retention_days: int = 365,
    now: datetime | None = None,
) -> RetentionCleanupResult:
    if not 1 <= batch_size <= 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    if failed_run_retention_days < 1 or audit_retention_days < 1:
        raise ValueError("Retention periods must be at least one day")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    run_cutoff = current - timedelta(days=failed_run_retention_days)
    audit_cutoff = current - timedelta(days=audit_retention_days)

    runs = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.status == "failed",
            ResearchRun.completed_at.isnot(None),
            ResearchRun.completed_at < run_cutoff,
            ~ResearchRun.document_associations.any(),
        )
        .order_by(ResearchRun.completed_at, ResearchRun.id)
        .limit(batch_size)
        .all()
    )
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.created_at < audit_cutoff)
        .order_by(AuditEvent.created_at, AuditEvent.id)
        .limit(batch_size)
        .all()
    )

    deleted_runs = 0
    deleted_events = 0
    if not dry_run:
        try:
            for run in runs:
                db.delete(run)
                deleted_runs += 1
            for event in events:
                db.delete(event)
                deleted_events += 1
            db.commit()
        except Exception:
            db.rollback()
            raise

    return RetentionCleanupResult(dry_run, len(runs), deleted_runs, len(events), deleted_events)
