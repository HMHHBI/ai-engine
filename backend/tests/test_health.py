import json
import logging
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

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
    logger = logging.getLogger("app.api.health")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)


@pytest.fixture
def client():
    return TestClient(app)


def test_liveness_probe_returns_200_without_dependencies(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_probe_returns_200_when_all_healthy(client):
    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=True
    ):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "checks": {
                "database": "ok",
                "redis": "ok",
            },
        }


def test_readiness_probe_returns_503_when_db_fails(client, log_capture):
    with patch("app.api.health._check_database", return_value=False), patch(
        "app.api.health._check_redis", return_value=True
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] == "error"
        assert data["checks"]["redis"] == "ok"


def test_readiness_probe_returns_503_when_redis_fails(client):
    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=False
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["redis"] == "error"


def test_readiness_probe_returns_503_when_both_fail(client):
    with patch("app.api.health._check_database", return_value=False), patch(
        "app.api.health._check_redis", return_value=False
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] == "error"
        assert data["checks"]["redis"] == "error"


def test_health_endpoints_do_not_require_authentication(client):
    live_res = client.get("/health/live")
    assert live_res.status_code == 200

    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=True
    ):
        ready_res = client.get("/health/ready")
        assert ready_res.status_code == 200


def test_readiness_probe_does_not_expose_credentials_in_response(client):
    secret = "mysecretpassword"
    with patch("app.api.health._check_database", return_value=False), patch(
        "app.api.health._check_redis", return_value=False
    ):
        response = client.get("/health/ready")
        body = json.dumps(response.json())
        assert secret not in body
