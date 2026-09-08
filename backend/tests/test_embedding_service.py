from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.services.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_empty_text_returns_none():
    assert (
        await EmbeddingService.generate_embedding("", model_provider="gemini") is None
    )
    assert (
        await EmbeddingService.generate_embedding("   ", model_provider="gemini")
        is None
    )


@pytest.mark.asyncio
async def test_missing_provider_returns_none():
    assert (
        await EmbeddingService.generate_embedding("sample text", model_provider="")
        is None
    )


@pytest.mark.asyncio
async def test_unknown_provider_returns_none():
    assert (
        await EmbeddingService.generate_embedding(
            "sample text", model_provider="unsupported_custom"
        )
        is None
    )


@pytest.mark.asyncio
async def test_gemini_success_returns_embedding(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "mock-test-key")

    mock_resp = httpx.Response(
        status_code=200,
        json={"embedding": {"values": [0.1, 0.2, 0.3]}},
        request=httpx.Request("POST", "https://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="gemini"
        )
        assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_gemini_http_error_returns_none(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "mock-test-key")

    mock_resp = httpx.Response(
        status_code=500,
        text="Internal upstream error body",
        request=httpx.Request("POST", "https://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="gemini"
        )
        assert vec is None


@pytest.mark.asyncio
async def test_gemini_timeout_returns_none(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "mock-test-key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="gemini"
        )
        assert vec is None


@pytest.mark.asyncio
async def test_ollama_success_returns_embedding():
    mock_resp = httpx.Response(
        status_code=200,
        json={"embedding": [0.4, 0.5, 0.6]},
        request=httpx.Request("POST", "http://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="ollama"
        )
        assert vec == [0.4, 0.5, 0.6]


@pytest.mark.asyncio
async def test_ollama_http_error_returns_none():
    mock_resp = httpx.Response(
        status_code=404,
        text="Model not found",
        request=httpx.Request("POST", "http://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="ollama"
        )
        assert vec is None


@pytest.mark.asyncio
async def test_ollama_timeout_returns_none():
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="ollama"
        )
        assert vec is None


@pytest.mark.asyncio
async def test_malformed_provider_response_returns_none():
    mock_resp = httpx.Response(
        status_code=200,
        json={"unexpected_field": "no embedding here"},
        request=httpx.Request("POST", "http://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        vec = await EmbeddingService.generate_embedding(
            "sample text", model_provider="ollama"
        )
        assert vec is None


@pytest.mark.asyncio
async def test_embedding_service_does_not_log_sensitive_content(caplog, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "secret-key-12345")

    sensitive_text = "SUPER_SECRET_PAYLOAD_CONTENT"
    sensitive_response_body = "SENSITIVE_UPSTREAM_DIAGNOSTICS_BODY"

    mock_resp = httpx.Response(
        status_code=400,
        text=sensitive_response_body,
        request=httpx.Request("POST", "https://mock.url"),
    )

    with caplog.at_level(logging.DEBUG):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await EmbeddingService.generate_embedding(
                sensitive_text, model_provider="gemini"
            )

    log_output = caplog.text
    assert sensitive_text not in log_output
    assert sensitive_response_body not in log_output
    assert "secret-key-12345" not in log_output

@pytest.mark.asyncio
async def test_generate_embedding_reused_client_lifecycle():
    """Verify that EmbeddingService reuses configured persistent client."""
    from unittest.mock import AsyncMock, MagicMock

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embedding": [0.1] * 768}
    mock_client.post = AsyncMock(return_value=mock_resp)

    EmbeddingService.set_client(mock_client)
    try:
        res = await EmbeddingService.generate_embedding("lifecycle test text", model_provider="ollama")
        assert res == [0.1] * 768
        assert mock_client.post.call_count == 1
    finally:
        EmbeddingService.set_client(None)

@pytest.mark.asyncio
async def test_generate_embedding_fallback_when_no_client():
    """Verify fallback to temporary client when lifecycle client is None."""
    from unittest.mock import AsyncMock, MagicMock, patch

    EmbeddingService.set_client(None)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": [0.2] * 768}
        mock_post.return_value = mock_resp

        res = await EmbeddingService.generate_embedding("fallback test text", model_provider="ollama")
        assert res == [0.2] * 768
