from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response, status
import redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["health"],
)


def _check_database() -> bool:
    """Execute cheap SELECT 1 query using existing engine."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.error(
            "health_dependency_failed",
            extra={
                "event": "health_dependency_failed",
                "dependency": "database",
            },
        )
        return False


def _check_redis() -> bool:
    """Perform isolated Redis PING with bounded timeout and explicit close."""
    client = None
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        return bool(client.ping())
    except Exception:
        logger.error(
            "health_dependency_failed",
            extra={
                "event": "health_dependency_failed",
                "dependency": "redis",
            },
        )
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


@router.get("/live")
def liveness_probe():
    """Liveness probe: confirms process is running and responsive."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_probe(response: Response):
    """Readiness probe: validates required external dependencies."""
    db_ok, redis_ok = await asyncio.gather(
        asyncio.to_thread(_check_database),
        asyncio.to_thread(_check_redis),
    )

    all_ready = db_ok and redis_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": {
            "database": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    }
