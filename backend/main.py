from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1_router import api_router
from app.core.config import settings
from app.db.session import engine
from app.db.models import Base

# 1. Database Tables Create Karna (Laravel Migration ki tarah)
# Note: Production mein hum Alembic use karte hain, lekin start ke liye ye best hai
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# 2. CORS Middleware (Frontend connection ke liye)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Aapke Vue frontend ka URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Static Files (Profile images ke liye)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 4. Main Router ko Include karna
app.include_router(api_router)

@app.get("/")
def home():
    return {"message": "Hassan AI Professional Backend is Running!"}