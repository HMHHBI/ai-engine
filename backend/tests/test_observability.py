import json
import logging
from unittest.mock import patch
import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.core.logging import StructuredJsonFormatter, configure_logging
from app.core.middleware import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    CorrelationIdMiddleware,
    correlation_id_var,
)
from fastapi import FastAPI


def test_structured_json_formatter_blocks_sensitive_fields():
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test event",
        args=(),
        exc_info=None,
    )
    record.event = "user_interaction"
    record.chat_id = 42
    record.prompt = "This is a private secret prompt."
    record.token = "bearer-secret-token"

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["event"] == "user_interaction"
    assert parsed["chat_id"] == 42
    assert parsed["prompt"] == "[REDACTED]"
    assert parsed["token"] == "[REDACTED]"


def test_correlation_id_generation_and_header_echo():
    test_app = FastAPI()
    test_app.add_middleware(CorrelationIdMiddleware)

    @test_app.get("/ping")
    def ping(request: Request):
        return {"id": request.state.correlation_id, "ctx": correlation_id_var.get()}

    client = TestClient(test_app)

    # 1. Fallback generates a UUID
    res = client.get("/ping")
    assert res.status_code == 200
    gen_id = res.headers.get(CORRELATION_ID_HEADER)
    assert gen_id is not None
    data = res.json()
    assert data["id"] == gen_id
    assert data["ctx"] == gen_id

    # 2. X-Correlation-ID takes precedence
    res = client.get("/ping", headers={CORRELATION_ID_HEADER: "custom-corr-123"})
    assert res.headers.get(CORRELATION_ID_HEADER) == "custom-corr-123"
    assert res.json()["id"] == "custom-corr-123"

    # 3. X-Request-ID supported as fallback
    res = client.get("/ping", headers={REQUEST_ID_HEADER: "req-456"})
    assert res.headers.get(CORRELATION_ID_HEADER) == "req-456"
    assert res.json()["id"] == "req-456"


def test_correlation_id_cleans_up_after_request():
    test_app = FastAPI()
    test_app.add_middleware(CorrelationIdMiddleware)

    @test_app.get("/clean")
    def clean():
        return {"status": "ok"}

    client = TestClient(test_app)
    client.get("/clean")
    # ContextVar must be reset back to None
    assert correlation_id_var.get(None) is None
