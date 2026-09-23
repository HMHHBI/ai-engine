from __future__ import annotations

import time
from unittest.mock import patch
import pytest


def test_google_auth_success_when_email_verified(client, db_session) -> None:
    ts = int(time.time() * 1000)
    mock_idinfo = {
        "email": f"google-verified-{ts}@example.com",
        "email_verified": True,
        "name": "Verified User",
        "picture": "https://example.com/photo.jpg",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_idinfo):
        resp = client.post("/auth/google", json={"token": "valid-mock-token"})

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == mock_idinfo["email"]


def test_google_auth_rejected_when_email_not_verified(client, db_session) -> None:
    ts = int(time.time() * 1000)
    mock_idinfo = {
        "email": f"google-unverified-{ts}@example.com",
        "email_verified": False,
        "name": "Unverified User",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_idinfo):
        resp = client.post("/auth/google", json={"token": "unverified-mock-token"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid Google Token"


def test_google_auth_rejected_when_email_verified_missing(client, db_session) -> None:
    ts = int(time.time() * 1000)
    mock_idinfo = {
        "email": f"google-missing-flag-{ts}@example.com",
        "name": "Missing Flag User",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_idinfo):
        resp = client.post("/auth/google", json={"token": "missing-flag-mock-token"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid Google Token"


def test_google_auth_rejected_when_token_payload_missing(client) -> None:
    resp = client.post("/auth/google", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Token missing"
