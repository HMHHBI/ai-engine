from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    # Validation & Client Errors
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # AI Provider Errors
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"

    # Streaming & Persistence
    STREAM_ERROR = "stream_error"
    PERSISTENCE_ERROR = "persistence_error"
    CLIENT_DISCONNECT = "client_disconnect"
    CANCELLED = "cancelled"

    # RAG & Ingestion
    RAG_FAILED = "rag_retrieval_failed"
    EXTRACTION_ERROR = "pdf_extraction_error"
    EMBEDDING_ERROR = "embedding_error"

    # Server Errors
    DATABASE_ERROR = "database_error"
    INTERNAL_ERROR = "unhandled_exception"


SAFE_CLIENT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests. Please wait a moment before trying again.",
    ErrorCode.PROVIDER_TIMEOUT: "The AI provider timed out. Please try again.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The AI provider is temporarily unavailable. Please try again.",
    ErrorCode.PROVIDER_ERROR: "Unable to complete the AI request.",
    ErrorCode.STREAM_ERROR: "Unable to complete the request right now.",
    ErrorCode.PERSISTENCE_ERROR: "Response generated but could not be saved. Please retry.",
    ErrorCode.CANCELLED: "AI stream cancelled.",
    ErrorCode.INTERNAL_ERROR: "An unexpected error occurred on the server.",
}
