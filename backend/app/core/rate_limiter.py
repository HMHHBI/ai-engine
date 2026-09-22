import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

# Test environment bypass flag
is_testing = os.getenv("TESTING", "false").lower() == "true"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=["200 per minute"],
    enabled=not is_testing
)
