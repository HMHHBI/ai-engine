from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.models import (
    Chat,
    Document,
    User,
    WorkspaceMembership,
)


def create_user(
    db_session: Session,
    *,
    email: str,
    name: str = "Workspace Test User",
) -> User:
    user = User(
        name=name,
        email=email,
        password="test-password-hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


def create_workspace(
    client: TestClient,
    user: User,
    *,
    name: str = "Test Workspace",
) -> dict:
    response = client.post(
        "/workspaces/",
        headers=auth_headers(user),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def activate_membership(
    db_session: Session,
    *,
    workspace_id: int,
    user_id: int,
) -> None:
    membership = (
        db_session.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .one()
    )
    membership.status = "active"
    db_session.commit()


def invite_member(
    client: TestClient,
    owner: User,
    workspace_id: int,
    member: User,
    role: str,
) -> dict:
    response = client.post(
        f"/workspaces/{workspace_id}/members",
        headers=auth_headers(owner),
        json={"email": member.email, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_creator_is_automatically_owner(
    client: TestClient,
    db_session: Session,
):
    user = create_user(db_session, email="workspace-owner@example.test")

    workspace = create_workspace(client, user)

    membership = (
        db_session.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace["id"],
            WorkspaceMembership.user_id == user.id,
        )
        .one()
    )

    assert workspace["created_by"] == user.id
    assert membership.role == "owner"
    assert membership.status == "active"


def test_other_user_cannot_read_update_or_delete_workspace(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(db_session, email="tenant-a@example.test")
    other_user = create_user(db_session, email="tenant-b@example.test")

    workspace = create_workspace(client, owner)
    workspace_id = workspace["id"]
    headers = auth_headers(other_user)

    read_response = client.get(
        f"/workspaces/{workspace_id}",
        headers=headers,
    )
    assert read_response.status_code == 404

    update_response = client.patch(
        f"/workspaces/{workspace_id}",
        headers=headers,
        json={"name": "Unauthorized change"},
    )
    assert update_response.status_code == 404

    delete_response = client.delete(
        f"/workspaces/{workspace_id}",
        headers=headers,
    )
    assert delete_response.status_code == 404

    owner_read_response = client.get(
        f"/workspaces/{workspace_id}",
        headers=auth_headers(owner),
    )
    assert owner_read_response.status_code == 200
    assert owner_read_response.json()["name"] == "Test Workspace"


def test_viewer_cannot_invite_members_or_attach_documents(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(db_session, email="viewer-owner@example.test")
    viewer = create_user(db_session, email="viewer@example.test")
    another_user = create_user(db_session, email="viewer-target@example.test")

    workspace = create_workspace(client, owner)
    workspace_id = workspace["id"]

    invite_member(client, owner, workspace_id, viewer, "viewer")
    activate_membership(
        db_session,
        workspace_id=workspace_id,
        user_id=viewer.id,
    )

    invite_response = client.post(
        f"/workspaces/{workspace_id}/members",
        headers=auth_headers(viewer),
        json={"email": another_user.email, "role": "researcher"},
    )
    assert invite_response.status_code == 403

    chat = Chat(user_id=owner.id, title="Legacy chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    document = Document(
        user_id=owner.id,
        chat_id=chat.id,
        filename="research.pdf",
        mime_type="application/pdf",
        status="ready",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    attach_response = client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=auth_headers(viewer),
        json={"document_ids": [document.id]},
    )
    assert attach_response.status_code == 403


def test_researcher_cannot_change_member_roles(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(db_session, email="research-owner@example.test")
    researcher = create_user(db_session, email="researcher@example.test")
    viewer = create_user(db_session, email="research-viewer@example.test")

    workspace = create_workspace(client, owner)
    workspace_id = workspace["id"]

    invite_member(client, owner, workspace_id, researcher, "researcher")
    invite_member(client, owner, workspace_id, viewer, "viewer")

    activate_membership(
        db_session,
        workspace_id=workspace_id,
        user_id=researcher.id,
    )
    activate_membership(
        db_session,
        workspace_id=workspace_id,
        user_id=viewer.id,
    )

    response = client.patch(
        f"/workspaces/{workspace_id}/members/{viewer.id}",
        headers=auth_headers(researcher),
        json={"role": "researcher"},
    )

    assert response.status_code == 403

    membership = (
        db_session.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == viewer.id,
        )
        .one()
    )
    assert membership.role == "viewer"


def test_workspace_association_does_not_change_legacy_chat_document_links(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(db_session, email="legacy-workflow@example.test")

    chat = Chat(
        user_id=owner.id,
        title="Existing single-document chat",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    document = Document(
        user_id=owner.id,
        chat_id=chat.id,
        filename="existing.pdf",
        mime_type="application/pdf",
        status="ready",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    workspace = create_workspace(client, owner)

    response = client.post(
        f"/workspaces/{workspace['id']}/documents",
        headers=auth_headers(owner),
        json={"document_ids": [document.id]},
    )

    assert response.status_code == 200, response.text
    assert any(item["document_id"] == document.id for item in response.json())

    db_session.expire_all()

    unchanged_document = (
        db_session.query(Document).filter(Document.id == document.id).one()
    )
    unchanged_chat = db_session.query(Chat).filter(Chat.id == chat.id).one()

    assert unchanged_document.chat_id == chat.id
    assert unchanged_document.user_id == owner.id
    assert unchanged_chat.id == chat.id
    assert any(
        linked_document.id == document.id
        for linked_document in unchanged_chat.documents
    )
