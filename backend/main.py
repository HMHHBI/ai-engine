import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1_router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

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