from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
import logging

logger = logging.getLogger(__name__)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Jab request limit exceed ho jaye to clean 429 response dena"""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "success": False,
            "error": "Rate limit exceeded",
            "detail": f"Too many requests. Please wait a moment before trying again.",
            "path": request.url.path
        }
    )

async def global_exception_handler(request: Request, exc: Exception):
    """Koi unexpected code crash ho to clean 500 error response dena"""
    logger.error(f"Unhandled Exception at {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred on the server.",
            "path": request.url.path
        }
    )