import sys
from pathlib import Path

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.repositories.user_repo import UserRepository
from app.core.security import hash_password
from app.db.models import User, Chat, Document

M3_TEST_EMAIL = "m3_test_user@example.com"
M3_TEST_PASSWORD = "Password123!"
M3_TEST_NAME = "M3 Test User"

USER2_EMAIL = "other_user@example.com"

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
        else:
            user.hashed_password = hash_password(M3_TEST_PASSWORD)
            db.commit()
            db.refresh(user)
        print(f"Verified & updated M3 test user: {user.email} (ID: {user.id})")

        # Seed User 2 for Cross-User Ownership Isolation Tests (M4 W9b)
        user2 = UserRepository.get_by_email(db, USER2_EMAIL)
        if not user2:
            user2 = UserRepository.create(
                db=db,
                name="Other Test User",
                email=USER2_EMAIL,
                password=M3_TEST_PASSWORD,
            )
        else:
            user2.hashed_password = hash_password(M3_TEST_PASSWORD)
            db.commit()
            db.refresh(user2)

        # Ensure User 2 has a chat session
        chat2 = db.query(Chat).filter(Chat.user_id == user2.id).first()
        if not chat2:
            chat2 = Chat(
                user_id=user2.id,
                title="User 2 Private Chat"
            )
            db.add(chat2)
            db.commit()
            db.refresh(chat2)

        doc2 = db.query(Document).filter(Document.user_id == user2.id).first()
        if not doc2:
            doc2 = Document(
                user_id=user2.id,
                chat_id=chat2.id,
                filename="user2_private.pdf",
                mime_type="application/pdf",
                file_size=1024,
                page_count=2,
                status="ready",
                storage_url="s3://dummy/user2_private.pdf"
            )
            db.add(doc2)
            db.commit()
            db.refresh(doc2)
        print(f"Seeded User 2 (ID: {user2.id}) and non-owned Doc (ID: {doc2.id})")

    finally:
        db.close()

if __name__ == "__main__":
    seed_m3()
