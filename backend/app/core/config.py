from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str
    VERSION: str
    
    # Database
    DATABASE_URL: str
    
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
    
    ALLOWED_ORIGINS: str = ""
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()