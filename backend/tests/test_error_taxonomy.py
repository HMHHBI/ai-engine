import json
import logging
from unittest.mock import patch
import pytest
from fastapi import Request
from starlette.testclient import TestClient

from app.core.error_codes import ErrorCode, SAFE_CLIENT_MESSAGES
from app.core.exceptions import AppError
from main import app


class MockLogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def log_capture():
    handler = MockLogCaptureHandler()
    logger = logging.getLogger("app.core.exceptions")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)


def test_error_codes_are_unique():
    values = [item.value for item in ErrorCode]
    assert len(values) == len(set(values)), "Error codes must be strictly unique"


def test_critical_codes_have_safe_messages():
    for code in [
        ErrorCode.PROVIDER_TIMEOUT,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.PROVIDER_ERROR,
        ErrorCode.STREAM_ERROR,
        ErrorCode.PERSISTENCE_ERROR,
        ErrorCode.RATE_LIMIT_EXCEEDED,
        ErrorCode.INTERNAL_ERROR,
    ]:
        assert code in SAFE_CLIENT_MESSAGES
        assert len(SAFE_CLIENT_MESSAGES[code]) > 0


def test_app_error_handler_formats_safely(log_capture):
    test_client = TestClient(app, raise_server_exceptions=False)

    @app.get("/test-app-error-route")
    async def trigger_app_error():
        raise AppError(code=ErrorCode.PROVIDER_TIMEOUT, status_code=504)

    response = test_client.get("/test-app-error-route")
    assert response.status_code == 504
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "provider_timeout"
    assert data["detail"] == SAFE_CLIENT_MESSAGES[ErrorCode.PROVIDER_TIMEOUT]

    logged = [
        r
        for r in log_capture.records
        if getattr(r, "event", None) == "application_error"
    ]
    assert len(logged) == 1
    assert logged[0].error_code == "provider_timeout"


def test_global_exception_handler_masks_traceback_from_client(log_capture):
    test_client = TestClient(app, raise_server_exceptions=False)

    @app.get("/test-crash-route")
    async def trigger_crash():
        raise RuntimeError("Secret DB credentials: postgresql://admin:secret123@db")

    response = test_client.get("/test-crash-route")
    assert response.status_code == 500
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Internal Server Error"
    assert "Secret DB credentials" not in json.dumps(data)
