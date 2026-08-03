from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str
    VERSION: str
    
    # Database
    DATABASE_URL: str
    
    # Frontend Reset URL
    FRONTEND_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    
    # AI Keys
    GEMINI_API_KEY: str
    
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
    
    # CORS Settings
    ALLOWED_ORIGINS: str = ""
    
    # Redis Settings
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_URL: str
    class Config:
        env_file = ".env"
        extra = "ignore"
        case_sensitive = True

settings = Settings()