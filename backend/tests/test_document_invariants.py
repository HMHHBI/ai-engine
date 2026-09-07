from __future__ import annotations

import time
import pytest
from app.core.security import create_access_token
from app.db.models import DocumentChunk
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository
from sqlalchemy import select


class DummyChunk:
    def __init__(self, text: str, page_number: int = 1, chunk_index: int = 0):
        self.text = text
        self.page_number = page_number
        self.chunk_index = chunk_index


@pytest.fixture()
def invariant_environment(db_session):
    ts = int(time.time() * 1000)
    user_a = UserRepository.create(
        db_session,
        name="User A",
        email=f"inv-a-{ts}@example.com",
        password="Password!123",
    )
    user_b = UserRepository.create(
        db_session,
        name="User B",
        email=f"inv-b-{ts}@example.com",
        password="Password!123",
    )
    chat_a = ChatRepository.create_chat(user_id=user_a.id)
    chat_b = ChatRepository.create_chat(user_id=user_b.id)

    return user_a, user_b, chat_a, chat_b


def test_document_chat_ownership_mismatch_rejected(invariant_environment):
    user_a, user_b, chat_a, chat_b = invariant_environment

    # Cannot create document in another user's chat
    res = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_b.id,  # User B's chat
        filename="mismatch.pdf",
        mime_type="application/pdf",
    )
    assert res is None


def test_full_document_lifecycle_and_chunk_cleanup(invariant_environment):
    user_a, _, chat_a, _ = invariant_environment

    # 1. Create (processing)
    doc = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="lifecycle.pdf",
        mime_type="application/pdf",
    )
    assert doc is not None
    assert doc.status == "processing"

    # 2. Store vectors
    dummy_vec = [0.25] * 768
    VectorRepository.replace_document_chunks(
        user_id=user_a.id,
        document_id=doc.id,
        chunks_with_embeddings=[(DummyChunk("Lifecycle passage", 1, 0), dummy_vec)],
    )

    # 3. Mark ready
    ready_doc = DocumentRepository.update_status(
        document_id=doc.id,
        user_id=user_a.id,
        status="ready",
    )
    assert ready_doc.status == "ready"

    # 4. Searchable via active document
    active = DocumentRepository.get_active_for_chat(
        chat_id=chat_a.id, user_id=user_a.id
    )
    assert active.id == doc.id
    results = VectorRepository.search_similar_chunks(
        user_id=user_a.id,
        document_id=active.id,
        query_vector=dummy_vec,
    )
    assert len(results) == 1

    # 5. Delete document
    deleted = DocumentRepository.delete(document_id=doc.id, user_id=user_a.id)
    assert deleted is True

    # 6. Verify document and its chunks are completely gone
    assert (
        DocumentRepository.get_owned_document(document_id=doc.id, user_id=user_a.id)
        is None
    )
    with session_scope() as db:
        chunks = (
            db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
            .scalars()
            .all()
        )
        assert len(chunks) == 0


def test_multi_document_active_precedence(invariant_environment):
    user_a, _, chat_a, _ = invariant_environment

    # Doc 1: ready
    d1 = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="d1.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=d1.id, user_id=user_a.id, status="ready"
    )

    # Doc 2: processing
    d2 = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="d2.pdf",
        mime_type="application/pdf",
    )

    # Active must still be d1
    assert (
        DocumentRepository.get_active_for_chat(chat_id=chat_a.id, user_id=user_a.id).id
        == d1.id
    )

    # Mark Doc 2 ready -> Doc 2 must become active
    DocumentRepository.update_status(
        document_id=d2.id, user_id=user_a.id, status="ready"
    )
    assert (
        DocumentRepository.get_active_for_chat(chat_id=chat_a.id, user_id=user_a.id).id
        == d2.id
    )

    # Doc 3: failed -> Active must remain d2
    d3 = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="d3.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=d3.id, user_id=user_a.id, status="failed", error_message="Failed"
    )
    assert (
        DocumentRepository.get_active_for_chat(chat_id=chat_a.id, user_id=user_a.id).id
        == d2.id
    )


def test_delete_isolation_does_not_affect_other_documents(invariant_environment):
    user_a, _, chat_a, _ = invariant_environment

    doc_1 = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="doc1.pdf",
        mime_type="application/pdf",
    )
    doc_2 = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="doc2.pdf",
        mime_type="application/pdf",
    )

    dummy_vec = [0.1] * 768
    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=doc_1.id,
        chunks_with_embeddings=[(DummyChunk("Chunk Doc 1", 1, 0), dummy_vec)],
    )
    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=doc_2.id,
        chunks_with_embeddings=[(DummyChunk("Chunk Doc 2", 1, 0), dummy_vec)],
    )

    # Delete doc 1
    DocumentRepository.delete(document_id=doc_1.id, user_id=user_a.id)

    # Verify doc 2 and its chunks remain untouched
    assert (
        DocumentRepository.get_owned_document(document_id=doc_2.id, user_id=user_a.id)
        is not None
    )
    with session_scope() as db:
        chunks_doc2 = (
            db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc_2.id)
            )
            .scalars()
            .all()
        )
        assert len(chunks_doc2) == 1
        assert (
            chunks_doc2[0].content == "Chunk Doc 1"
            or chunks_doc2[0].content == "Chunk Doc 2"
        )
        assert chunks_doc2[0].content == "Chunk Doc 2"


def test_patch_metadata_cannot_mutate_status_or_ownership(
    client, invariant_environment
):
    user_a, user_b, chat_a, _ = invariant_environment
    token = create_access_token(user_id=user_a.id)
    headers = {"Authorization": f"Bearer {token}"}

    doc = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="original.pdf",
        mime_type="application/pdf",
    )

    # Attempt to inject user_id, chat_id, or status via PATCH
    res = client.patch(
        f"/documents/{doc.id}",
        json={
            "filename": "updated.pdf",
            "status": "ready",
            "user_id": user_b.id,
            "chat_id": 9999,
        },
        headers=headers,
    )
    assert res.status_code == 200

    # Verify status remained "processing" and ownership untouched
    current = DocumentRepository.get_owned_document(
        document_id=doc.id, user_id=user_a.id
    )
    assert current.filename == "updated.pdf"
    assert current.status == "processing"
    assert current.user_id == user_a.id
    assert current.chat_id == chat_a.id
