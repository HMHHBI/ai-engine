from fastapi import APIRouter
from app.api import auth, chat, user, test  # Apne controllers import karein

api_router = APIRouter()

# Laravel ke Route::group ki tarah yahan hum routes ko jorh rahe hain
api_router.include_router(test.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(user.router)
# Agay ja kar agar aap 'user.py' banate hain toh wo bhi yahan add hoga