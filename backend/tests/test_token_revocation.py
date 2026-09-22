from __future__ import annotations

import time
import pytest
from app.core.security import create_access_token
from app.repositories.user_repo import UserRepository


def test_password_reset_invalidates_preexisting_jwt(client, db_session) -> None:
    ts = int(time.time() * 1000)
    email = f"revoke-test-{ts}@example.com"
    old_password = "OldPassword!123"
    new_password = "NewPassword!456"

    # 1. Create user and obtain token at initial version
    user = UserRepository.create(
        db_session,
        name="Revoke User",
        email=email,
        password=old_password,
    )
    initial_version = user.token_version
    assert initial_version == 1

    pre_reset_token = create_access_token(user_id=user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {pre_reset_token}"}

    # Verify token works before reset
    resp = client.get("/user/me", headers=headers)
    assert resp.status_code == 200

    # 2. Trigger forgot-password flow and consume reset token
    user, raw_token = UserRepository.create_reset_token(db_session, email)
    assert raw_token is not None

    user_by_token = UserRepository.get_by_valid_reset_token(db_session, raw_token)
    assert user_by_token is not None

    UserRepository.consume_reset_token(db_session, user_by_token, new_password)

    db_session.refresh(user)
    assert user.token_version == initial_version + 1

    # 3. Old pre-reset token MUST now be rejected with 401
    resp_after = client.get("/user/me", headers=headers)
    assert resp_after.status_code == 401
    assert "revoked" in resp_after.json()["detail"].lower()

    # 4. New token issued with updated version MUST work
    new_token = create_access_token(user_id=user.id, token_version=user.token_version)
    new_headers = {"Authorization": f"Bearer {new_token}"}
    resp_new = client.get("/user/me", headers=new_headers)
    assert resp_new.status_code == 200


def test_token_without_version_claim_is_rejected(client, db_session) -> None:
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Legacy Token User",
        email=f"legacy-{ts}@example.com",
        password="Password!123",
    )

    # Simulate token missing "v" claim entirely
    import jwt
    from datetime import datetime, timezone, timedelta
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": "legacy-test-id",
    }
    unversioned_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    resp = client.get("/user/me", headers={"Authorization": f"Bearer {unversioned_jwt}"})
    assert resp.status_code == 401
    assert "revoked" in resp.json()["detail"].lower()
