from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.dialects.postgresql import insert
from app.db.models import AIUsageEvent
from app.db.session import session_scope
from app.services.pricing_service import resolve_price

logger = logging.getLogger(__name__)

_ALLOWED_PROVIDERS = {"openai", "gemini", "ollama"}
_ALLOWED_SOURCES = {"provider_reported", "estimated", "unavailable"}
_ALLOWED_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


def new_usage_ids() -> tuple[str, str]:
    req_id = str(uuid.uuid4())
    idemp_key = f"usage_{req_id}_{uuid.uuid4().hex[:12]}"
    return req_id, idemp_key


def _clean_token_int(val: Any) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        as_int = int(val)
        return as_int if as_int >= 0 else None
    except (ValueError, TypeError):
        return None


def normalize_usage(
    raw: dict[str, Any] | None,
) -> tuple[int | None, int | None, int | None, str]:
    if not isinstance(raw, dict):
        return None, None, None, "unavailable"

    # Explicit lookup taake 0 falsy hokar drop na ho
    inp_raw = raw.get("input_tokens") if "input_tokens" in raw else raw.get("prompt_tokens")
    out_raw = raw.get("output_tokens") if "output_tokens" in raw else raw.get("completion_tokens")
    tot_raw = raw.get("total_tokens")

    inp = _clean_token_int(inp_raw)
    out = _clean_token_int(out_raw)
    tot = _clean_token_int(tot_raw)

    if tot is None and inp is not None and out is not None:
        tot = inp + out

    if inp is None and out is None and tot is None:
        return None, None, None, "unavailable"

    return inp, out, tot, "provider_reported"


def record_usage(
    *,
    request_id: str,
    idempotency_key: str,
    provider: str,
    model: str,
    usage: dict[str, Any] | None,
    provider_metadata: dict[str, Any] | None = None,
    user_id: int | None = None,
    chat_id: int | None = None,
    message_id: int | None = None,
    operation: str = "chat",
    status: str = "succeeded",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    input_tokens, output_tokens, total_tokens, source = normalize_usage(usage)
    start_time = started_at or datetime.now(timezone.utc)
    comp_time = completed_at or datetime.now(timezone.utc)
    norm_status = status if status in _ALLOWED_STATUSES else "succeeded"

    with session_scope() as db:
        price_quote = resolve_price(
            db,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            invocation_time=start_time,
        )

        cost_amount = price_quote.amount if price_quote else None
        cost_currency = price_quote.currency if price_quote else "USD"
        pricing_version = price_quote.pricing_version if price_quote else None
        pricing_snapshot = price_quote.snapshot if price_quote else None

        stmt = (
            insert(AIUsageEvent)
            .values(
                request_id=request_id,
                idempotency_key=idempotency_key,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                provider=provider,
                model=model,
                operation=operation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                usage_source=source,
                status=norm_status,
                cost_amount=cost_amount,
                cost_currency=cost_currency,
                pricing_version=pricing_version,
                pricing_snapshot=pricing_snapshot,
                provider_metadata=provider_metadata or {},
                started_at=start_time,
                completed_at=comp_time,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )
        db.execute(stmt)
