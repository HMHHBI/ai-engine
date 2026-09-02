from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


# ============================================================
# Password hashing
# ============================================================


def hash_password(password: str) -> str:
    """
    Hash a user password using bcrypt.

    Password validation belongs at the schema/API boundary.
    This function intentionally does not impose password policy.
    """

    if not password:
        raise ValueError("Password cannot be empty.")

    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Safely verify a plaintext password against its hash.
    """

    if not plain_password or not hashed_password:
        return False

    try:
        return pwd_context.verify(
            plain_password,
            hashed_password,
        )
    except (ValueError, TypeError):
        return False


# ============================================================
# JWT
# ============================================================


def create_access_token(
    user_id: int,
) -> str:
    """
    Create a short-lived authenticated access token.

    Claims:
        sub: authenticated user ID
        type: access token
        iat: issued-at timestamp
        exp: expiration timestamp
        jti: unique token ID
    """

    if user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_hex(16),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token(
    token: str,
) -> dict[str, Any] | None:
    """
    Decode and validate an access JWT.

    Returns:
        Validated claims dictionary.

    Returns None for:
        - malformed token
        - invalid signature
        - expired token
        - wrong token type
        - missing/invalid subject

    Never leaks JWT verification details to callers.
    """

    if not token or not isinstance(token, str):
        return None

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        if payload.get("type") != "access":
            return None

        subject = payload.get("sub")

        if not subject:
            return None

        try:
            user_id = int(subject)
        except (TypeError, ValueError):
            return None

        if user_id <= 0:
            return None

        payload["user_id"] = user_id

        return payload

    except ExpiredSignatureError:
        return None

    except JWTError:
        return None


# ============================================================
# Password reset tokens
# ============================================================


def generate_password_reset_token() -> str:
    """
    Generate a cryptographically secure password-reset token.

    The raw token is intended ONLY for the reset URL/email.
    Never store the raw value in the database.
    """

    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """
    SHA-256 hash for password-reset token storage.

    Reset tokens are already generated with high entropy, so a fast
    cryptographic hash is appropriate here. The raw token is never
    persisted.
    """

    if not token:
        raise ValueError("Reset token cannot be empty.")

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_reset_token(
    token: str,
    token_hash: str,
) -> bool:
    """
    Constant-time verification of a raw reset token against its
    stored SHA-256 hash.
    """

    if not token or not token_hash:
        return False

    calculated_hash = hash_reset_token(token)

    return secrets.compare_digest(
        calculated_hash,
        token_hash,
    )
