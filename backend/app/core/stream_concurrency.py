import asyncio
import logging
import secrets
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Atomic compare-and-delete Lua script:
# Only delete the lease if the stored token matches ARGV[1]
_LUA_RELEASE_LEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_redis_client: Optional[aioredis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None


def get_redis_client() -> aioredis.Redis:
    """
    Obtain or initialize the shared async Redis client.
    Guarantees client is bound to the currently running event loop.
    """
    global _redis_client, _redis_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is None or _redis_loop is not current_loop:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        _redis_loop = current_loop

    return _redis_client


def build_lease_key(user_id: int) -> str:
    """Format Redis key for user stream lease."""
    return f"ai:stream:lease:{user_id}"


async def acquire_stream_lease(
    user_id: int,
    ttl_seconds: Optional[int] = None,
    client: Optional[aioredis.Redis] = None,
) -> Optional[str]:
    """
    Atomically acquire an active stream lease for a user using SET NX EX.
    Returns the unique lease token on success, or None if a lease is already held.
    """
    if ttl_seconds is None:
        ttl_seconds = settings.AI_STREAM_LEASE_TTL_SECONDS

    redis = client or get_redis_client()
    key = build_lease_key(user_id)
    token = secrets.token_hex(16)

    acquired = await redis.set(key, token, nx=True, ex=ttl_seconds)
    if acquired:
        logger.info(
            "Acquired stream lease for user_id=%s token=%s ttl=%s",
            user_id,
            token,
            ttl_seconds,
        )
        return token

    logger.warning(
        "Failed to acquire stream lease for user_id=%s: lease already held",
        user_id,
    )
    return None


async def release_stream_lease(
    user_id: int,
    lease_token: str,
    client: Optional[aioredis.Redis] = None,
) -> bool:
    """
    Atomically release the stream lease only if the stored token matches lease_token.
    Prevents stale workers from releasing newly acquired leases of subsequent streams.
    """
    if not lease_token:
        return False

    redis = client or get_redis_client()
    key = build_lease_key(user_id)

    try:
        deleted = await redis.eval(_LUA_RELEASE_LEASE, 1, key, lease_token)
        released = bool(deleted == 1)
        if released:
            logger.info("Released stream lease for user_id=%s token=%s", user_id, lease_token)
        else:
            logger.warning(
                "Lease release skipped for user_id=%s token=%s: token mismatch or expired",
                user_id,
                lease_token,
            )
        return released
    except Exception:
        logger.exception("Unexpected error releasing stream lease for user_id=%s", user_id)
        return False
