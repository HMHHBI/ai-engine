import json
import sys
from pathlib import Path

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from sqlalchemy.orm import Session
from sqlalchemy.sql import text
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

        # Seed Workspace & Attach Documents for User
        workspace_name = "Neural Research Lab"
        ws_res = db.execute(
            text("""
                SELECT id FROM workspaces
                WHERE created_by = :uid AND name = :name
                ORDER BY id ASC LIMIT 1
            """),
            {"uid": user.id, "name": workspace_name},
        ).scalar_one_or_none()

        if ws_res is None:
            ws_res = db.execute(
                text("""
                    INSERT INTO workspaces (name, created_by, created_at, updated_at)
                    VALUES (:name, :uid, NOW(), NOW())
                    RETURNING id
                """),
                {"name": workspace_name, "uid": user.id},
            ).scalar_one()

        # Ensure the test user has active owner membership
        db.execute(
            text("""
                INSERT INTO workspace_memberships (
                    workspace_id, user_id, role, status,
                    created_at, updated_at
                )
                VALUES (
                    :ws_id, :uid, 'owner', 'active', NOW(), NOW()
                )
                ON CONFLICT (workspace_id, user_id)
                DO UPDATE SET
                    role = 'owner',
                    status = 'active',
                    updated_at = NOW()
            """),
            {"ws_id": ws_res, "uid": user.id},
        )

        # Attach documents owned by the test user
        user_documents = (
            db.query(Document)
            .filter(Document.user_id == user.id)
            .all()
        )
        for doc_obj in user_documents:
            db.execute(
                text("""
                    INSERT INTO workspace_documents (
                        workspace_id, document_id, added_by, added_at
                    )
                    VALUES (
                        :ws_id, :doc_id, :uid, NOW()
                    )
                    ON CONFLICT (workspace_id, document_id)
                    DO NOTHING
                """),
                {
                    "ws_id": ws_res,
                    "doc_id": doc_obj.id,
                    "uid": user.id,
                },
            )
        db.commit()
        print(f"Seeded workspace {ws_res} ({workspace_name}) for test user {user.id}.")
        print("Seeded Workspace ID 1 (Neural Research Lab) and attached documents.")

        # Write deterministic fixture state for E2E tests
        target_dirs = [
            Path(__file__).resolve().parent.parent.parent / "frontend" / "e2e" / "fixtures",
            Path("/app/frontend/e2e/fixtures"),
            Path("/frontend/e2e/fixtures"),
        ]
        fixture_data = {
            "user1_email": user.email,
            "user1_id": user.id,
            "user2_email": user2.email,
            "user2_id": user2.id,
            "user2_chat_id": chat2.id,
            "user2_doc_id": doc2.id,
        }
        for fdir in target_dirs:
            try:
                fdir.mkdir(parents=True, exist_ok=True)
                with open(fdir / "test_seed_state.json", "w") as f:
                    json.dump(fixture_data, f, indent=2)
                print(f"Wrote seed fixture state to {fdir / 'test_seed_state.json'}")
            except Exception:
                pass

    finally:
        db.close()

if __name__ == "__main__":
    seed_m3()
