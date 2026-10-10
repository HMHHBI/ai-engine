from __future__ import annotations

import asyncio
import time
from functools import wraps
from typing import Any, Callable

from fastapi import Response
from prometheus_client import (
    Gauge,
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

# 1. Chat SSE Streams
CHAT_STREAMS = Counter(
    "ai_chat_streams_total",
    "Total SSE chat streams processed",
    ["status"],
)

CHAT_STREAM_DURATION = Histogram(
    "ai_chat_stream_duration_seconds",
    "Duration of chat streaming sessions in seconds",
    ["status"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

CHAT_TIME_TO_FIRST_TOKEN = Histogram(
    "ai_chat_time_to_first_token_seconds",
    "Time from stream start to first emitted token",
    ["provider", "model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
)

# 2. Token Consumption
TOKENS_CONSUMED = Counter(
    "ai_tokens_consumed_total",
    "Tokens consumed recorded by ledger",
    ["provider", "model", "direction", "status", "source"],
)

# 3. Document Ingestion
DOCUMENT_INGESTIONS = Counter(
    "ai_document_ingestions_total",
    "Document ingestion job execution count",
    ["outcome"],
)

DOCUMENT_INGESTION_DURATION = Histogram(
    "ai_document_ingestion_duration_seconds",
    "Duration of document ingestion jobs in seconds",
    ["outcome"],
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0),
)

# 4. Redis Stream Queue Lag
DOCUMENT_QUEUE_LAG = Histogram(
    "ai_document_queue_lag_seconds",
    "Age of document job stream message upon processing pickup",
    buckets=(0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0),
)



def refresh_redis_gauges() -> None:
    """Refresh DLQ and pending queue gauges directly from Redis."""
    try:
        from app.core.redis import get_redis_client
        import redis
        client = get_redis_client()
        # 1. DLQ messages count
        dlq_len = client.xlen("ingestion:dlq")
        DOCUMENT_DLQ_MESSAGES.set(dlq_len)
        
        # 2. Pending messages count in document-workers group
        pending_info = client.xpending("ai:document:jobs", "document-workers")
        pending_count = pending_info["pending"] if isinstance(pending_info, dict) else (pending_info[0] if pending_info else 0)
        DOCUMENT_QUEUE_PENDING_MESSAGES.set(pending_count)
    except Exception:
        # Avoid breaking /metrics if Redis is temporarily unreachable
        pass


def metrics_response() -> Response:
    """Generate Prometheus scrape format response."""
    refresh_redis_gauges()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def observe_chat_stream(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        status = "succeeded"
        try:
            async for item in func(*args, **kwargs):
                yield item
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "failed"
            raise
        finally:
            CHAT_STREAMS.labels(status=status).inc()
            CHAT_STREAM_DURATION.labels(status=status).observe(
                max(0.0, time.monotonic() - started)
            )

    return wrapped


def observe_time_to_first_token(*, provider: str, model: str, seconds: float) -> None:
    if seconds >= 0:
        CHAT_TIME_TO_FIRST_TOKEN.labels(provider=provider, model=model).observe(seconds)


def record_token_consumption(
    *,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    status: str,
    source: str,
) -> None:
    for direction, value in (("input", input_tokens), ("output", output_tokens)):
        if value is not None and value >= 0:
            TOKENS_CONSUMED.labels(
                provider=provider,
                model=model,
                direction=direction,
                status=status,
                source=source,
            ).inc(value)


def observe_async_operation(
    operation: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if operation != "document_ingestion":
        raise ValueError(f"Unsupported metrics operation: {operation}")

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            outcome = "succeeded"
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception:
                outcome = "failed"
                raise
            finally:
                DOCUMENT_INGESTIONS.labels(outcome=outcome).inc()
                DOCUMENT_INGESTION_DURATION.labels(outcome=outcome).observe(
                    max(0.0, time.monotonic() - started)
                )

        return wrapped

    return decorate


def observe_document_queue_lag(message_id: str) -> None:
    try:
        timestamp_ms = int(message_id.split("-", 1)[0])
    except (TypeError, ValueError, AttributeError):
        return
    lag_seconds = max(0.0, time.time() - (timestamp_ms / 1000.0))
    DOCUMENT_QUEUE_LAG.observe(lag_seconds)

# 5. LLM Provider Requests & Error Tracking
LLM_PROVIDER_REQUESTS = Counter(
    "ai_llm_provider_requests_total",
    "LLM provider request outcomes",
    ["provider", "outcome"],
)

# 6. DLQ Depth & Worker Health Gauges
DOCUMENT_DLQ_MESSAGES = Gauge(
    "ai_document_dlq_messages",
    "Current number of entries in the document ingestion DLQ",
)

DOCUMENT_QUEUE_PENDING_MESSAGES = Gauge(
    "ai_document_queue_pending_messages",
    "Pending entries in the document worker consumer group",
)

DOCUMENT_WORKER_LAST_SUCCESS = Gauge(
    "ai_document_worker_last_success_timestamp_seconds",
    "Unix timestamp of the most recent successful document ingestion",
)


def record_llm_provider_request(*, provider: str, outcome: str) -> None:
    LLM_PROVIDER_REQUESTS.labels(provider=provider, outcome=outcome).inc()


def set_document_dlq_depth(count: int) -> None:
    DOCUMENT_DLQ_MESSAGES.set(max(0, count))


def set_document_queue_pending(count: int) -> None:
    DOCUMENT_QUEUE_PENDING_MESSAGES.set(max(0, count))


def record_document_worker_success() -> None:
    DOCUMENT_WORKER_LAST_SUCCESS.set(time.time())
