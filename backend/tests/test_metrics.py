import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from app.core.metrics import (
    observe_document_queue_lag,
    observe_time_to_first_token,
    record_token_consumption,
)


def test_token_metrics_accept_known_provider_usage():
    record_token_consumption(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=12,
        output_tokens=8,
        status="succeeded",
        source="provider_reported",
    )


def test_token_metrics_skip_unknown_values():
    record_token_consumption(
        provider="gemini",
        model="gemini-2.5-flash",
        input_tokens=None,
        output_tokens=None,
        status="succeeded",
        source="unavailable",
    )


def test_time_to_first_token_accepts_nonnegative_duration():
    observe_time_to_first_token(
        provider="openai",
        model="gpt-4o-mini",
        seconds=0.25,
    )


def test_queue_lag_ignores_malformed_stream_id():
    observe_document_queue_lag("not-a-stream-id")


def test_queue_lag_accepts_valid_stream_id():
    observe_document_queue_lag("1700000000000-0")


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200_and_prometheus_format():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        body = response.text
        assert "ai_tokens_consumed_total" in body
        assert "ai_chat_streams_total" in body


def test_provider_and_worker_metrics_track_values():
    from app.core.metrics import (
        record_llm_provider_request,
        set_document_dlq_depth,
        set_document_queue_pending,
        record_document_worker_success,
    )
    record_llm_provider_request(provider="openai", outcome="success")
    record_llm_provider_request(provider="gemini", outcome="error")
    set_document_dlq_depth(3)
    set_document_queue_pending(5)
    record_document_worker_success()
