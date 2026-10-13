import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.db.models import Chat, Document, User, WorkspaceMembership

ROLES = ("viewer", "researcher", "admin", "owner")

def make_user(db: Session, email: str) -> User:
    row = User(name="RBAC test", email=email, password="test-hash", is_active=True, token_version=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id=user.id, token_version=user.token_version)}"}

def make_workspace(client: TestClient, owner: User) -> dict:
    response = client.post("/workspaces/", headers=headers(owner), json={"name": "RBAC matrix"})
    assert response.status_code == 201, response.text
    return response.json()

def set_role(db: Session, workspace_id: int, user_id: int, role: str) -> None:
    row = db.query(WorkspaceMembership).filter_by(workspace_id=workspace_id, user_id=user_id).one_or_none()
    if row is None:
        row = WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role, status="active")
        db.add(row)
    else:
        row.role, row.status = role, "active"
    db.commit()

def owned_document(db: Session, user: User) -> Document:
    chat = Chat(user_id=user.id, title="RBAC chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    doc = Document(user_id=user.id, chat_id=chat.id, filename="rbac.pdf", mime_type="application/pdf", status="ready")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@pytest.mark.parametrize("role", ROLES)
def test_all_roles_can_read_workspace(client: TestClient, db_session: Session, role: str):
    owner = make_user(db_session, f"rbac-read-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-read-actor-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    response = client.get(f"/workspaces/{ws['id']}", headers=headers(actor))
    assert response.status_code == 200, response.text

@pytest.mark.parametrize(("role", "expected"), [("viewer", 403), ("researcher", 403), ("admin", 200), ("owner", 200)])
def test_workspace_update_role_matrix(client: TestClient, db_session: Session, role: str, expected: int):
    owner = make_user(db_session, f"rbac-up-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-up-actor-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    response = client.patch(f"/workspaces/{ws['id']}", headers=headers(actor), json={"name": "changed"})
    assert response.status_code == expected, response.text

@pytest.mark.parametrize(("role", "expected"), [("viewer", 403), ("researcher", 200), ("admin", 200), ("owner", 200)])
def test_document_attach_role_matrix(client: TestClient, db_session: Session, role: str, expected: int):
    owner = make_user(db_session, f"rbac-doc-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-doc-actor-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    doc = owned_document(db_session, actor)
    response = client.post(f"/workspaces/{ws['id']}/documents", headers=headers(actor), json={"document_ids": [doc.id]})
    assert response.status_code == expected, response.text

@pytest.mark.parametrize(("role", "expected"), [("viewer", 403), ("researcher", 403), ("admin", 201), ("owner", 201)])
def test_invite_member_role_matrix(client: TestClient, db_session: Session, role: str, expected: int):
    owner = make_user(db_session, f"rbac-invite-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-invite-actor-{role}@example.test")
    target = make_user(db_session, f"rbac-target-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    response = client.post(f"/workspaces/{ws['id']}/members", headers=headers(actor), json={"email": target.email, "role": "researcher"})
    assert response.status_code == expected, response.text

@pytest.mark.parametrize(("role", "expected"), [("viewer", 403), ("researcher", 403), ("admin", 403), ("owner", 204)])
def test_delete_workspace_role_matrix(client: TestClient, db_session: Session, role: str, expected: int):
    owner = make_user(db_session, f"rbac-del-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-del-actor-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    response = client.delete(f"/workspaces/{ws['id']}", headers=headers(actor))
    assert response.status_code == expected, response.text

@pytest.mark.parametrize("role", ROLES)
def test_all_roles_can_list_workspace_documents(client: TestClient, db_session: Session, role: str):
    owner = make_user(db_session, f"rbac-list-owner-{role}@example.test")
    actor = make_user(db_session, f"rbac-list-actor-{role}@example.test")
    ws = make_workspace(client, owner)
    set_role(db_session, ws["id"], actor.id, role)
    response = client.get(f"/workspaces/{ws['id']}/documents", headers=headers(actor))
    assert response.status_code == 200, response.text

def test_membership_in_other_workspace_does_not_grant_access(client: TestClient, db_session: Session):
    owner_a = make_user(db_session, "rbac-tenant-a@example.test")
    owner_b = make_user(db_session, "rbac-tenant-b@example.test")
    actor = make_user(db_session, "rbac-tenant-actor@example.test")
    ws_a = make_workspace(client, owner_a)
    ws_b = make_workspace(client, owner_b)
    set_role(db_session, ws_a["id"], actor.id, "owner")
    response = client.get(f"/workspaces/{ws_b['id']}", headers=headers(actor))
    assert response.status_code == 404
