from __future__ import annotations
import pytest
from sqlalchemy.orm import Session
from app.db.models import AuditEvent, User, Workspace
from app.services.audit_log import record_audit_event, sanitize_metadata


def test_sanitize_metadata_strips_sensitive_data():
    raw_data = {
        "user_id": 10,
        "password": "super-secret-password",
        "access_token": "jwt-token-string",
        "refresh_token": "refresh-token-val",
        "api_key": "sk-12345",
        "query": "Sensitive clinical query text",
        "answer": "Sensitive answer generation",
        "content": "Raw document content",
        "excerpt": "Evidence chunk excerpt",
        "safe_count": 5,
        "nested": {
            "token": "nested-token",
            "role": "admin",
        },
    }
    sanitized = sanitize_metadata(raw_data)
    assert "password" not in sanitized
    assert "access_token" not in sanitized
    assert "refresh_token" not in sanitized
    assert "api_key" not in sanitized
    assert "query" not in sanitized
    assert "answer" not in sanitized
    assert "content" not in sanitized
    assert "excerpt" not in sanitized
    assert sanitized["user_id"] == 10
    assert sanitized["safe_count"] == 5
    assert "token" not in sanitized["nested"]
    assert sanitized["nested"]["role"] == "admin"


def test_record_audit_event_persists_safely(db_session: Session):
    user = User(name="Audit Actor", email="audit_actor@example.com", password="pw", is_active=True, token_version=1)
    db_session.add(user)
    db_session.commit()

    ws = Workspace(name="Audit WS", created_by=user.id)
    db_session.add(ws)
    db_session.commit()

    event = record_audit_event(
        db_session,
        action="workspace.document_attached",
        resource_type="document",
        resource_id="101",
        actor_id=user.id,
        workspace_id=ws.id,
        outcome="success",
        metadata={
            "document_id": 101,
            "filename": "quarterly_results.pdf",
            "content": "Should be redacted",
        },
        ip_address="192.168.1.1",
        user_agent="pytest-client",
    )
    db_session.commit()

    assert event is not None
    stored = db_session.query(AuditEvent).filter(AuditEvent.id == event.id).first()
    assert stored is not None
    assert stored.action == "workspace.document_attached"
    assert stored.outcome == "success"
    assert stored.metadata_payload.get("document_id") == 101
    assert "content" not in stored.metadata_payload
