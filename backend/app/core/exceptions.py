from __future__ import annotations

import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.error_codes import ErrorCode, SAFE_CLIENT_MESSAGES

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application exception with canonical error code and safe client message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        super().__init__(
            message or SAFE_CLIENT_MESSAGES.get(code, "An error occurred.")
        )
        self.code = code
        self.message = message or SAFE_CLIENT_MESSAGES.get(code, "An error occurred.")
        self.status_code = status_code


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Clean 429 response when rate limit is exceeded."""
    logger.warning(
        "rate_limit_exceeded",
        extra={
            "event": ErrorCode.RATE_LIMIT_EXCEEDED.value,
            "error_code": ErrorCode.RATE_LIMIT_EXCEEDED.value,
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
            "detail": SAFE_CLIENT_MESSAGES[ErrorCode.RATE_LIMIT_EXCEEDED],
            "error_code": ErrorCode.RATE_LIMIT_EXCEEDED.value,
            "path": request.url.path,
        },
    )


async def app_error_handler(request: Request, exc: AppError):
    """Structured handler for classified application errors."""
    logger.error(
        "application_error",
        extra={
            "event": "application_error",
            "error_code": exc.code.value,
            "exception_type": exc.__class__.__name__,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.code.value,
            "detail": exc.message,
            "path": request.url.path,
        },
    )


async def global_exception_handler(request: Request, exc: Exception):
    """Structured 500 error logging without leaking internal crash details to clients."""
    logger.error(
        "unhandled_exception",
        exc_info=True,
        extra={
            "event": ErrorCode.INTERNAL_ERROR.value,
            "error_code": ErrorCode.INTERNAL_ERROR.value,
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
            "detail": SAFE_CLIENT_MESSAGES[ErrorCode.INTERNAL_ERROR],
            "error_code": ErrorCode.INTERNAL_ERROR.value,
            "path": request.url.path,
        },
    )
