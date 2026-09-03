import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.middleware import correlation_id_var

# Fields that MUST NEVER be serialized into operational logs
BLOCKED_KEYS = {
    "prompt",
    "prompt_text",
    "completion",
    "response_text",
    "file_context",
    "pdf_context",
    "extracted_text",
    "chunk_content",
    "image_base64",
    "token",
    "jwt",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "api_key",
}


class StructuredJsonFormatter(logging.Formatter):
    """
    Standardizes operational application logs into valid JSON structures.
    Guarantees correlation ID attachment and blocks sensitive keys.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "correlation_id": correlation_id_var.get(None),
        }

        # Extract extra fields passed via extra={...}
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "event",
        }

        for key, val in record.__dict__.items():
            if key in standard_attrs:
                continue
            lower_key = key.lower()
            if lower_key in BLOCKED_KEYS:
                log_entry[key] = "[REDACTED]"
            else:
                log_entry[key] = val

        # Handle exception tracebacks if present
        if record.exc_info:
            log_entry["exception_type"] = (
                record.exc_info[0].__name__
                if record.exc_info[0]
                else "UnknownException"
            )
            log_entry["exception_message"] = str(record.exc_info[1])
            if record.exc_text:
                log_entry["stack_trace"] = record.exc_text
            else:
                log_entry["stack_trace"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    """Configures the root and app loggers to use the JSON formatter on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Suppress verbose third-party loggers
    for logger_name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
    ):
        l = logging.getLogger(logger_name)
        l.handlers.clear()
        l.addHandler(handler)
        l.propagate = False
