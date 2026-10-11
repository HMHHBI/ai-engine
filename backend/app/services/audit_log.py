from __future__ import annotations
import logging
from typing import Any
from sqlalchemy.orm import Session
from app.db.models import AuditEvent

logger = logging.getLogger("app.audit")

REDACTED_KEYS = {
    "password", "token", "access_token", "refresh_token", "secret", "authorization",
    "prompt", "query", "answer", "content", "cookie", "api_key", "excerpt"
}


def sanitize_metadata(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    clean: dict[str, Any] = {}
    for k, v in data.items():
        if k.lower() in REDACTED_KEYS:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            clean[k] = v
        elif isinstance(v, (list, tuple)):
            clean[k] = [item for item in v if isinstance(item, (str, int, float, bool))][:10]
        elif isinstance(v, dict):
            clean[k] = sanitize_metadata(v)
    return clean


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    actor_id: int | None = None,
    workspace_id: int | None = None,
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent | None:
    try:
        clean_meta = sanitize_metadata(metadata)
        event = AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            actor_id=actor_id,
            workspace_id=workspace_id,
            outcome=outcome,
            metadata_payload=clean_meta,
            ip_address=ip_address[:45] if ip_address else None,
            user_agent=user_agent[:255] if user_agent else None,
        )
        db.add(event)
        db.flush()
        return event
    except Exception as exc:
        logger.error(f"Failed to record audit event '{action}': {exc}", exc_info=True)
        return None
