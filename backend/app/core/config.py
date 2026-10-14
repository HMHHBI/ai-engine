import os
from enum import Enum
from typing import List, Optional, Union, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIProvider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENAI = "openai"


class AIModel(str, Enum):
    OLLAMA_LLAMA_3_2 = "llama3.2"
    OLLAMA_DEEPSEEK_R1 = "deepseek-r1"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    OPENAI_GPT_4O_MINI = "gpt-4o-mini"


class EmbeddingProvider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Application & Environment
    # ------------------------------------------------------------------

    PROJECT_NAME: str = "Hassan AI Engine"
    VERSION: str = "1.0.0"
    APP_ENV: str = "development"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    DATABASE_URL: str

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    DB_DEPLOYMENT_CONNECTION_BUDGET: int = 100

    # ------------------------------------------------------------------
    # Frontend / CORS
    # ------------------------------------------------------------------

    FRONTEND_URL: str
    ALLOWED_ORIGINS: str = ""

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # ------------------------------------------------------------------
    # File Upload Security
    # ------------------------------------------------------------------

    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_PDF_PAGES: int = 100
    MAX_EXTRACTED_TEXT_CHARS: int = 2_000_000
    MAX_DOCUMENT_CHUNKS: int = 5_000
    MAX_CHUNK_EMBEDDINGS: int = 5_000

    # ------------------------------------------------------------------
    # Payload & AI Request Limits
    # ------------------------------------------------------------------

    MAX_PROMPT_CHARS: int = 32_000
    MAX_FILE_CONTEXT_CHARS: int = 100_000
    MAX_IMAGE_COUNT: int = 4
    MAX_IMAGE_BASE64_CHARS: int = 7_000_000  # ~5 MiB raw binary
    MAX_TOTAL_IMAGE_BASE64_CHARS: int = 20_000_000  # ~15 MiB aggregate binary

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------

    DEFAULT_AI_PROVIDER: AIProvider = AIProvider.OLLAMA
    DEFAULT_AI_MODEL: AIModel = AIModel.OLLAMA_LLAMA_3_2
    DEFAULT_EMBEDDING_PROVIDER: EmbeddingProvider = EmbeddingProvider.OLLAMA
    ENABLE_RERANKING: bool = False
    RERANKER_PROVIDER: str = "deterministic"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_BATCH_SIZE: int = 8
    RERANKER_DEVICE: str = "cpu"

    # ------------------------------------------------------------------
    # AI Timeout / Lifecycle Configuration
    # ------------------------------------------------------------------

    AI_CONNECT_TIMEOUT: float = 10.0
    AI_READ_TIMEOUT: float = 60.0
    AI_WRITE_TIMEOUT: float = 10.0
    AI_POOL_TIMEOUT: float = 5.0

    AI_REQUEST_TIMEOUT: float = 120.0
    AI_STREAM_MAX_SECONDS: float = 120.0

    # Gemini worker lifecycle
    GEMINI_MAX_WORKERS: int = 4
    GEMINI_WORKER_JOIN_TIMEOUT: float = 0.5
    GEMINI_QUEUE_SIZE: int = 32
    GEMINI_QUEUE_POLL_SECONDS: float = 0.25

    # ------------------------------------------------------------------
    # AI API Keys
    # ------------------------------------------------------------------

    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # ------------------------------------------------------------------
    # Google OAuth
    # ------------------------------------------------------------------

    GOOGLE_CLIENT_ID: Optional[str] = None

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None

    # ------------------------------------------------------------------
    # Cloudinary
    # ------------------------------------------------------------------

    CLOUDINARY_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379"

    # AI Stream Concurrency & Workload Budget
    AI_STREAM_CONCURRENCY_LIMIT: int = 1
    AI_STREAM_MAX_DURATION_SECONDS: int = 120
    AI_STREAM_LEASE_TTL_SECONDS: int = 180
    HEARTBEAT_INTERVAL_SECONDS: float = 15.0

    # Document Worker Concurrency & Recovery Settings
    DOCUMENT_WORKER_CONCURRENCY: int = 4
    DOCUMENT_JOB_STALE_AFTER_SECONDS: float = 60.0
    DOCUMENT_JOB_RECOVERY_INTERVAL_SECONDS: float = 15.0
    DOCUMENT_JOB_RECOVERY_BATCH_SIZE: int = 10
    DOCUMENT_JOB_RECOVERY_IDLE_SECONDS: float = 60.0
    DOCUMENT_JOB_READ_COUNT: int = 5

    # ------------------------------------------------------------------
    # Storage Configuration
    # ------------------------------------------------------------------

    STORAGE_BACKEND: Literal["local", "r2"] = "local"
    LOCAL_STORAGE_ROOT: str = "./storage"

    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_BUCKET_NAME: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "r2"}:
            raise ValueError("STORAGE_BACKEND must be either 'local' or 'r2'.")
        return normalized

    @field_validator(
        "MAX_UPLOAD_SIZE_BYTES",
        "MAX_PDF_PAGES",
        "MAX_EXTRACTED_TEXT_CHARS",
        "MAX_DOCUMENT_CHUNKS",
        "MAX_CHUNK_EMBEDDINGS",
        "MAX_PROMPT_CHARS",
        "MAX_FILE_CONTEXT_CHARS",
        "MAX_IMAGE_COUNT",
        "MAX_IMAGE_BASE64_CHARS",
        "MAX_TOTAL_IMAGE_BASE64_CHARS",
        mode="before",
    )
    @classmethod
    def validate_upload_limits(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("Upload security limits must be positive.")
        return int(value)

    @field_validator(
        "DB_POOL_SIZE",
        "DB_MAX_OVERFLOW",
        "DB_POOL_TIMEOUT",
        "DB_POOL_RECYCLE",
        "DB_DEPLOYMENT_CONNECTION_BUDGET",
        "AI_CONNECT_TIMEOUT",
        "AI_READ_TIMEOUT",
        "AI_WRITE_TIMEOUT",
        "AI_POOL_TIMEOUT",
        "AI_REQUEST_TIMEOUT",
        "AI_STREAM_MAX_SECONDS",
        "GEMINI_MAX_WORKERS",
        "GEMINI_WORKER_JOIN_TIMEOUT",
        "GEMINI_QUEUE_SIZE",
        "GEMINI_QUEUE_POLL_SECONDS",
        mode="before",
    )
    @classmethod
    def validate_positive_infrastructure_values(cls, value: float) -> float:
        if float(value) <= 0:
            raise ValueError("Infrastructure and timeout settings must be positive.")
        return value

    @model_validator(mode="after")
    def validate_aggregate_connection_budget(self) -> "Settings":
        if self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW > self.DB_DEPLOYMENT_CONNECTION_BUDGET:
            raise ValueError(
                f"Single-process pool capacity ({self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW}) "
                f"exceeds DB_DEPLOYMENT_CONNECTION_BUDGET ({self.DB_DEPLOYMENT_CONNECTION_BUDGET})"
            )
        return self

    @model_validator(mode="after")
    def validate_production_hardening(self) -> "Settings":
        if self.APP_ENV.lower() == "production":
            if self.SECRET_KEY in {"CHANGE_ME_TO_A_RANDOM_SECRET", "supersecretkey", "secret"}:
                raise ValueError("Production SECRET_KEY cannot be a placeholder or common default.")
            if len(self.SECRET_KEY) < 32:
                raise ValueError("Production SECRET_KEY must be at least 32 characters long.")
            
            origins = [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
            if not origins or "*" in origins:
                raise ValueError("Production requires explicit ALLOWED_ORIGINS (wildcard '*' disallowed).")
        return self


settings = Settings()
