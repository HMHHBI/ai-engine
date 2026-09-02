# backend/tests/test_security.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_token,
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
    verify_reset_token,
)

# ============================================================
# Password hashing
# ============================================================


def test_password_hash_is_not_plaintext() -> None:
    password = "StrongPassword!123"

    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2")


def test_password_hash_is_unique_per_call() -> None:
    password = "StrongPassword!123"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_password_verification_accepts_correct_password() -> None:
    password = "StrongPassword!123"

    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_password_verification_rejects_wrong_password() -> None:
    hashed = hash_password("StrongPassword!123")

    assert verify_password("WrongPassword!123", hashed) is False


def test_password_verification_handles_empty_values() -> None:
    assert verify_password("", "") is False
    assert verify_password("", "invalid-hash") is False
    assert verify_password("password", "") is False


# ============================================================
# JWT
# ============================================================


def test_create_access_token_contains_required_claims() -> None:
    token = create_access_token(user_id=123)

    payload = decode_token(token)

    assert payload is not None
    assert payload["user_id"] == 123
    assert payload["sub"] == "123"
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload
    assert "jti" in payload


def test_decode_valid_access_token() -> None:
    token = create_access_token(user_id=123)

    payload = decode_token(token)

    assert payload is not None
    assert payload["user_id"] == 123


def test_decode_token_rejects_empty_token() -> None:
    assert decode_token("") is None


def test_decode_token_rejects_garbage() -> None:
    assert decode_token("this-is-not-a-jwt") is None


def test_decode_token_rejects_tampered_token() -> None:
    token = create_access_token(user_id=123)

    parts = token.split(".")

    assert len(parts) == 3

    # Modify the payload without recalculating the signature.
    parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")

    tampered_token = ".".join(parts)

    assert decode_token(tampered_token) is None


def test_decode_token_rejects_wrong_secret() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "test-jti",
        },
        "completely-wrong-secret",
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_expired_token() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(minutes=1),
            "jti": "expired-jti",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_missing_subject() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "missing-sub",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_invalid_subject() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "not-an-integer",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "invalid-sub",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_zero_user_id() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "0",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "zero-user",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_negative_user_id() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "-1",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "negative-user",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


def test_decode_token_rejects_wrong_token_type() -> None:
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "refresh-token",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_token(token) is None


# ============================================================
# Password-reset tokens
# ============================================================


def test_password_reset_token_is_cryptographically_random() -> None:
    first = generate_password_reset_token()
    second = generate_password_reset_token()

    assert first
    assert second
    assert first != second
    assert len(first) >= 40


def test_reset_token_hash_is_sha256_hex() -> None:
    token = "test-reset-token"

    token_hash = hash_reset_token(token)

    assert len(token_hash) == 64
    assert all(character in "0123456789abcdef" for character in token_hash)


def test_reset_token_hash_is_deterministic() -> None:
    token = generate_password_reset_token()

    assert hash_reset_token(token) == hash_reset_token(token)


def test_reset_token_verification_accepts_correct_token() -> None:
    token = generate_password_reset_token()
    token_hash = hash_reset_token(token)

    assert (
        verify_reset_token(
            token,
            token_hash,
        )
        is True
    )


def test_reset_token_verification_rejects_wrong_token() -> None:
    token = generate_password_reset_token()
    token_hash = hash_reset_token(token)

    assert (
        verify_reset_token(
            "different-token",
            token_hash,
        )
        is False
    )


def test_reset_token_verification_rejects_empty_token() -> None:
    token = generate_password_reset_token()
    token_hash = hash_reset_token(token)

    assert (
        verify_reset_token(
            "",
            token_hash,
        )
        is False
    )


def test_reset_token_verification_rejects_empty_hash() -> None:
    token = generate_password_reset_token()

    assert (
        verify_reset_token(
            token,
            "",
        )
        is False
    )


# ============================================================
# Password-reset expiration + replay
# ============================================================


def test_password_reset_token_expiration_and_replay(
    db_session,
) -> None:
    from datetime import datetime, timedelta, timezone

    from app.repositories.user_repo import UserRepository

    user, raw_token = UserRepository.create_reset_token(
        db_session,
        "security-test@example.com",
        expires_minutes=30,
    )

    # Depending on your existing database state, the user may not
    # exist yet. Create it explicitly if necessary.
    if user is None:
        user = UserRepository.create(
            db_session,
            name="Security Test User",
            email="security-test@example.com",
            password="StrongPassword!123",
        )

        user, raw_token = UserRepository.create_reset_token(
            db_session,
            "security-test@example.com",
            expires_minutes=30,
        )

    assert user is not None
    assert raw_token is not None

    # Raw token must not be stored.
    assert user.reset_token_hash != raw_token
    assert len(user.reset_token_hash) == 64

    # Valid token works.
    valid_user = UserRepository.get_by_valid_reset_token(
        db_session,
        raw_token,
    )

    assert valid_user is not None
    assert valid_user.id == user.id

    # Consume it.
    UserRepository.consume_reset_token(
        db_session,
        valid_user,
        "NewSecurePassword!456",
    )

    # Same token must now fail.
    replayed_user = UserRepository.get_by_valid_reset_token(
        db_session,
        raw_token,
    )

    assert replayed_user is None


def test_expired_reset_token_is_rejected(db_session) -> None:
    from app.repositories.user_repo import UserRepository

    user = UserRepository.create(
        db_session,
        name="Expired Reset User",
        email="expired-reset@example.com",
        password="StrongPassword!123",
    )

    raw_token = generate_password_reset_token()

    user.reset_token_hash = hash_reset_token(raw_token)
    user.reset_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    db_session.commit()
    db_session.refresh(user)

    result = UserRepository.get_by_valid_reset_token(
        db_session,
        raw_token,
    )

    assert result is None
