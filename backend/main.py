from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.v1_router import api_router
from app.core.config import settings
from app.core.exceptions import (
    global_exception_handler,
    rate_limit_exceeded_handler,
)
from app.core.rate_limiter import limiter

# Database imports
import app.db.models  # Ensures all models are registered
from app.db.session import engine

logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# LIFESPAN CONTEXT MANAGER
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB & Extensions
    logger.info("Initializing database connection and pgvector extension.")

    try:
        with engine.connect() as conn:
            # Verify database connectivity and enable pgvector.
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

        logger.info("Database connection verified and pgvector extension initialized.")

    except Exception as exc:
        logger.exception(
            "Fatal database initialization failure during application startup."
        )
        raise RuntimeError(
            "Application startup failed: database initialization is unavailable."
        ) from exc

    yield

    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# 1. Attach Limiter to App State & Rate Limit Handler
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,
)
app.add_exception_handler(
    Exception,
    global_exception_handler,
)

# 2. CORS Middleware Configuration
if not settings.ALLOWED_ORIGINS.strip():
    raise RuntimeError(
        "ALLOWED_ORIGINS must be explicitly configured. "
        "Wildcard CORS is not permitted."
    )

origins = [
    origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()
]

if not origins:
    raise RuntimeError("ALLOWED_ORIGINS must contain at least one valid origin.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Main API Router Integration
app.include_router(api_router)


@app.get("/")
def home():
    return {"message": "Hassan AI Professional Backend is Running!"}
