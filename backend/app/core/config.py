from enum import Enum
from typing import Optional

from pydantic import field_validator
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
    # Application
    # ------------------------------------------------------------------

    PROJECT_NAME: str = "Hassan AI Engine"
    VERSION: str = "1.0.0"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    DATABASE_URL: str

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

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
    # AI
    # ------------------------------------------------------------------

    DEFAULT_AI_PROVIDER: AIProvider = AIProvider.OLLAMA
    DEFAULT_AI_MODEL: AIModel = AIModel.OLLAMA_LLAMA_3_2
    DEFAULT_EMBEDDING_PROVIDER: EmbeddingProvider = EmbeddingProvider.OLLAMA

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Provider/model consistency validation
    # ------------------------------------------------------------------

    @field_validator("DEFAULT_AI_MODEL")
    @classmethod
    def validate_default_model(cls, model: AIModel) -> AIModel:
        return model

    # ------------------------------------------------------------------
    # Upload Validation
    # ------------------------------------------------------------------

    @field_validator(
        "MAX_UPLOAD_SIZE_BYTES",
        "MAX_PDF_PAGES",
        "MAX_EXTRACTED_TEXT_CHARS",
        "MAX_DOCUMENT_CHUNKS",
        "MAX_CHUNK_EMBEDDINGS",
        mode="before",
    )
    @classmethod
    def validate_upload_limits(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("Upload security limits must be positive.")
        return int(value)

    # ------------------------------------------------------------------
    # Infrastructure Validation
    # ------------------------------------------------------------------

    @field_validator(
        "DB_POOL_SIZE",
        "DB_MAX_OVERFLOW",
        "DB_POOL_TIMEOUT",
        "DB_POOL_RECYCLE",
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


settings = Settings()