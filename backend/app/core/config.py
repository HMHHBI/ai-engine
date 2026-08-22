from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str
    VERSION: str

    # CORS Settings
    ALLOWED_ORIGINS: str = ""

    # Database
    DATABASE_URL: str

    # Frontend Reset URL
    FRONTEND_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # AI CONFIGURATION
    DEFAULT_AI_PROVIDER: str  # Provider used when the user/chat does not explicitly have a provider assigned.
    DEFAULT_AI_MODEL: str  # Default LLM model for the selected provider.
    DEFAULT_EMBEDDING_PROVIDER: str # Provider used to generate document/query embeddings.

    # AI API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Ollama
    OLLAMA_BASE_URL: str
    OLLAMA_LLM_MODEL: str
    OLLAMA_EMBED_MODEL: str

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None

    # Email Settings
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None

    # Cloudinary Settings
    CLOUDINARY_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # Redis Settings
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_URL: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        case_sensitive = True

settings = Settings()
