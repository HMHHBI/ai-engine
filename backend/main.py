import os
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.rate_limiter import limiter
from app.core.exceptions import rate_limit_exceeded_handler, global_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1_router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# Attach Limiter to App State
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Add Handlers
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 2. CORS Middleware (Frontend connection ke liye)
origins = [
    origin.strip()
    for origin in settings.ALLOWED_ORIGINS.split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Main Router ko Include karna
app.include_router(api_router)

@app.get("/")
def home():
    return {"message": "Hassan AI Professional Backend is Running!"}