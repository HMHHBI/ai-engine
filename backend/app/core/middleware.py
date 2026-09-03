import uuid
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"

correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates a canonical correlation ID for each incoming HTTP request.
    Stores it in ContextVar, request.state, and echoes it back in the response headers.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Precedence: X-Correlation-ID -> X-Request-ID -> Generated UUID4
        incoming_id = request.headers.get(CORRELATION_ID_HEADER) or request.headers.get(
            REQUEST_ID_HEADER
        )
        correlation_id = incoming_id.strip() if incoming_id else str(uuid.uuid4())

        # Set in ContextVar & request state
        token = correlation_id_var.set(correlation_id)
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            # Reset ContextVar to prevent cross-request leakage in thread pools
            correlation_id_var.reset(token)
