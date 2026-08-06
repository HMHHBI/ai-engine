from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.v1_router import api_router
from app.core.config import settings
from app.core.exceptions import global_exception_handler, rate_limit_exceeded_handler
from app.core.rate_limiter import limiter

# Database imports
import app.db.models  # Ensures all models are registered
from app.db.session import Base, engine


# -------------------------------------------------------------
# LIFESPAN CONTEXT MANAGER (Modern Replacement for @app.on_event)
# -------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB & Extensions
    try:
        with engine.connect() as conn:
            # Enable pgvector extension automatically
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            print("✅ Successfully enabled pgvector extension.")

        # Create all tables (users, chats, document_chunks, etc.)
        # Base.metadata.create_all(bind=engine)
        # print("✅ All database tables synchronized successfully.")
    except Exception as e:
        print(f"❌ Error initializing database on startup: {e}")

    yield  # Application runs here

    # Shutdown logic (if any cleanup is required in future)
    print("🛑 Application shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# 1. Attach Limiter to App State & Rate Limit Handler
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 2. CORS Middleware Configuration
origins = (
    [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
    if settings.ALLOWED_ORIGINS
    else ["*"]
)

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
