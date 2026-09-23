import os
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import decode_token

is_testing = os.getenv("TESTING", "false").lower() == "true"


def user_or_ip_key(request: Request) -> str:
    path = request.scope.get("path", "")
    if path.startswith("/auth/"):
        return f"ip:{get_remote_address(request)}"

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() == "bearer":
        token = token.strip()
        if token:
            payload = decode_token(token)
            if payload:
                user_id = payload.get("user_id")
                if user_id is not None:
                    return f"user:{user_id}"

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=user_or_ip_key,
    storage_uri=settings.REDIS_URL,
    default_limits=["200 per minute"],
    enabled=not is_testing,
)
