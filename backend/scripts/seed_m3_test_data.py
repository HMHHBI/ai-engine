import os
import sys

# Ensure backend root is on sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.repositories.user_repo import UserRepository
from app.core.security import hash_password
from app.db.models import User

M3_TEST_EMAIL = "m3_test_user@example.com"
M3_TEST_PASSWORD = "Password123!"
M3_TEST_NAME = "M3 Test User"

def seed_m3():
    db: Session = SessionLocal()
    try:
        user = UserRepository.get_by_email(db, M3_TEST_EMAIL)
        if not user:
            user = UserRepository.create(
                db=db,
                name=M3_TEST_NAME,
                email=M3_TEST_EMAIL,
                password=M3_TEST_PASSWORD,
            )
            print(f"Created M3 test user: {user.email} (ID: {user.id})")
        else:
            user.password = hash_password(M3_TEST_PASSWORD)
            db.commit()
            print(f"Verified & updated M3 test user: {user.email} (ID: {user.id})")
    finally:
        db.close()

if __name__ == "__main__":
    seed_m3()
