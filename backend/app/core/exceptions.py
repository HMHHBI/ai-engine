import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Clean 429 response when rate limit is exceeded."""
    logger.warning(
        "rate_limit_exceeded",
        extra={
            "event": "rate_limit_exceeded",
            "path": request.url.path,
            "method": request.method,
            "status_code": 429,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "success": False,
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please wait a moment before trying again.",
            "path": request.url.path,
        },
    )


async def global_exception_handler(request: Request, exc: Exception):
    """Structured 500 error logging without leaking internal crash details to clients."""
    logger.error(
        "unhandled_exception",
        exc_info=True,
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__,
            "status_code": 500,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred on the server.",
            "path": request.url.path,
        },
    )
