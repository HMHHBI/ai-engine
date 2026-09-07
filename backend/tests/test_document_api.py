from __future__ import annotations

import time
import pytest
from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture()
def two_users_and_documents(db_session):
    ts = int(time.time() * 1000)
    user_a = UserRepository.create(
        db_session,
        name="User A",
        email=f"docapi-a-{ts}@example.com",
        password="Password!123",
    )
    user_b = UserRepository.create(
        db_session,
        name="User B",
        email=f"docapi-b-{ts}@example.com",
        password="Password!123",
    )
    chat_a = ChatRepository.create_chat(user_id=user_a.id)
    chat_b = ChatRepository.create_chat(user_id=user_b.id)

    doc_a = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="doc_a.pdf",
        mime_type="application/pdf",
    )
    doc_b = DocumentRepository.create(
        user_id=user_b.id,
        chat_id=chat_b.id,
        filename="doc_b.pdf",
        mime_type="application/pdf",
    )
    return user_a, user_b, chat_a, chat_b, doc_a, doc_b


def test_list_chat_documents_owner_success(client, two_users_and_documents):
    user_a, _, chat_a, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_a.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/documents/chat/{chat_a.id}", headers=headers)
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 1
    assert docs[0]["id"] == doc_a.id
    assert docs[0]["filename"] == "doc_a.pdf"


def test_list_chat_documents_cross_user_rejected(client, two_users_and_documents):
    _, user_b, chat_a, _, _, _ = two_users_and_documents
    token = create_access_token(user_id=user_b.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/documents/chat/{chat_a.id}", headers=headers)
    assert res.status_code == 404


def test_get_document_owner_success(client, two_users_and_documents):
    user_a, _, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_a.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/documents/{doc_a.id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == doc_a.id
    assert res.json()["filename"] == "doc_a.pdf"


def test_get_document_cross_user_rejected(client, two_users_and_documents):
    _, user_b, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_b.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/documents/{doc_a.id}", headers=headers)
    assert res.status_code == 404


def test_update_document_owner_success(client, two_users_and_documents):
    user_a, _, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_a.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/documents/{doc_a.id}",
        json={"filename": "renamed_doc.pdf", "page_count": 12},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["filename"] == "renamed_doc.pdf"
    assert res.json()["page_count"] == 12


def test_update_document_cross_user_rejected(client, two_users_and_documents):
    _, user_b, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_b.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/documents/{doc_a.id}",
        json={"filename": "hacked.pdf"},
        headers=headers,
    )
    assert res.status_code == 404


def test_delete_document_owner_success(client, two_users_and_documents):
    user_a, _, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_a.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/documents/{doc_a.id}", headers=headers)
    assert res.status_code == 204

    get_res = client.get(f"/documents/{doc_a.id}", headers=headers)
    assert get_res.status_code == 404


def test_delete_document_cross_user_rejected(client, two_users_and_documents):
    _, user_b, _, _, doc_a, _ = two_users_and_documents
    token = create_access_token(user_id=user_b.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.delete(f"/documents/{doc_a.id}", headers=headers)
    assert res.status_code == 404

    token_a = create_access_token(user_id=two_users_and_documents[0].id)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    get_res = client.get(f"/documents/{doc_a.id}", headers=headers_a)
    assert get_res.status_code == 200
