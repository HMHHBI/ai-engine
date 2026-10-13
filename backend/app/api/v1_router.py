from fastapi import APIRouter
from app.api import (
    auth,
    chat,
    user,
    health,
    documents,
    workspaces,
    research,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(user.router)
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(workspaces.router)
api_router.include_router(research.router)
