from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

# Redis URL ke sath Rate Limiter initialize kar rahe hain
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=["200 per minute"]  # Default limit for all endpoints
)