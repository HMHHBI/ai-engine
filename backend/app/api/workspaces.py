from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.models import (
    Document,
    User,
    Workspace,
    WorkspaceDocument,
    WorkspaceMembership,
)
from app.db.session import get_db
from app.schemas.workspace_schema import (
    WorkspaceCreate,
    WorkspaceDocumentAttach,
    WorkspaceDocumentOut,
    WorkspaceMemberInvite,
    WorkspaceMembershipOut,
    WorkspaceMemberRoleUpdate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services.workspace_auth import require_workspace_role

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _membership_response(
    membership: WorkspaceMembership,
) -> WorkspaceMembershipOut:
    return WorkspaceMembershipOut(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        user_email=membership.user.email,
        user_name=membership.user.name,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _workspace_document_response(
    association: WorkspaceDocument,
) -> WorkspaceDocumentOut:
    document = association.document
    return WorkspaceDocumentOut(
        document_id=document.id,
        chat_id=document.chat_id,
        filename=document.filename,
        mime_type=document.mime_type,
        status=document.status,
        added_by=association.added_by,
        added_at=association.added_at,
    )


def _get_workspace_membership(
    db: Session,
    workspace_id: int,
    user_id: int,
) -> WorkspaceMembership | None:
    return (
        db.query(WorkspaceMembership)
        .options(joinedload(WorkspaceMembership.user))
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .first()
    )


@router.post(
    "/",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = Workspace(
        name=payload.name.strip(),
        created_by=current_user.id,
    )

    if not workspace.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workspace name cannot be blank.",
        )

    db.add(workspace)
    db.flush()

    owner_membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="owner",
        status="active",
    )
    db.add(owner_membership)
    db.commit()
    db.refresh(workspace)

    return workspace


@router.get("/", response_model=list[WorkspaceOut])
def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Workspace)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == Workspace.id,
        )
        .filter(
            WorkspaceMembership.user_id == current_user.id,
            WorkspaceMembership.status == "active",
        )
        .order_by(Workspace.created_at.desc(), Workspace.id.desc())
        .all()
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: int,
    access: WorkspaceMembership = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    access: WorkspaceMembership = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided.",
        )

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Workspace name cannot be blank.",
            )
        workspace.name = name

    workspace.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(workspace)

    return workspace


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workspace(
    workspace_id: int,
    access: WorkspaceMembership = Depends(require_workspace_role("owner")),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    db.delete(workspace)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def invite_workspace_member(
    workspace_id: int,
    payload: WorkspaceMemberInvite,
    current_user: User = Depends(get_current_user),
    access: WorkspaceMembership = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    requested_role = payload.role.value

    if requested_role == "owner":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ownership cannot be assigned through member invitations.",
        )

    if access.role == "admin" and requested_role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can invite administrators.",
        )

    target_user = (
        db.query(User)
        .filter(func.lower(User.email) == payload.email.strip().lower())
        .first()
    )

    if target_user is None or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="An active account with this email was not found.",
        )

    existing = _get_workspace_membership(
        db,
        workspace_id=workspace_id,
        user_id=target_user.id,
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user already has a workspace membership.",
        )

    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=target_user.id,
        role=requested_role,
        status="invited",
    )

    db.add(membership)
    db.commit()
    db.refresh(membership)

    membership = (
        db.query(WorkspaceMembership)
        .options(joinedload(WorkspaceMembership.user))
        .filter(WorkspaceMembership.id == membership.id)
        .one()
    )

    return _membership_response(membership)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMembershipOut,
)
def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    payload: WorkspaceMemberRoleUpdate,
    access: WorkspaceMembership = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    target = _get_workspace_membership(db, workspace_id, user_id)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace membership not found.",
        )

    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The workspace owner role cannot be changed here.",
        )

    requested_role = payload.role.value

    if requested_role == "owner":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ownership cannot be assigned through role updates.",
        )

    if access.role == "admin" and (target.role == "admin" or requested_role == "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can change administrator roles.",
        )

    target.role = requested_role
    target.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(target)

    target = (
        db.query(WorkspaceMembership)
        .options(joinedload(WorkspaceMembership.user))
        .filter(WorkspaceMembership.id == target.id)
        .one()
    )

    return _membership_response(target)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMembershipOut,
)
def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    access: WorkspaceMembership = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    target = _get_workspace_membership(db, workspace_id, user_id)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace membership not found.",
        )

    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The workspace owner cannot be removed.",
        )

    if access.role == "admin" and target.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can remove administrators.",
        )

    response = _membership_response(target)
    db.delete(target)
    db.commit()

    return response


@router.post(
    "/{workspace_id}/documents",
    response_model=list[WorkspaceDocumentOut],
    status_code=status.HTTP_200_OK,
)
def attach_workspace_documents(
    workspace_id: int,
    payload: WorkspaceDocumentAttach,
    current_user: User = Depends(get_current_user),
    access: WorkspaceMembership = Depends(require_workspace_role("researcher")),
    db: Session = Depends(get_db),
):
    requested_ids = list(dict.fromkeys(payload.document_ids))

    if len(requested_ids) != len(payload.document_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplicate document IDs are not allowed.",
        )

    documents = (
        db.query(Document)
        .filter(
            Document.id.in_(requested_ids),
            Document.user_id == current_user.id,
        )
        .all()
    )

    if len(documents) != len(requested_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more documents were not found or are not owned by you.",
        )

    existing_ids = {
        row[0]
        for row in (
            db.query(WorkspaceDocument.document_id)
            .filter(
                WorkspaceDocument.workspace_id == workspace_id,
                WorkspaceDocument.document_id.in_(requested_ids),
            )
            .all()
        )
    }

    for document in documents:
        if document.id not in existing_ids:
            db.add(
                WorkspaceDocument(
                    workspace_id=workspace_id,
                    document_id=document.id,
                    added_by=current_user.id,
                )
            )

    db.commit()

    associations = (
        db.query(WorkspaceDocument)
        .options(joinedload(WorkspaceDocument.document))
        .filter(WorkspaceDocument.workspace_id == workspace_id)
        .order_by(WorkspaceDocument.added_at.asc())
        .all()
    )

    return [_workspace_document_response(association) for association in associations]


@router.get(
    "/{workspace_id}/documents",
    response_model=list[WorkspaceDocumentOut],
)
def list_workspace_documents(
    workspace_id: int,
    access: WorkspaceMembership = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
):
    associations = (
        db.query(WorkspaceDocument)
        .options(joinedload(WorkspaceDocument.document))
        .filter(WorkspaceDocument.workspace_id == workspace_id)
        .order_by(WorkspaceDocument.added_at.asc())
        .all()
    )

    return [_workspace_document_response(association) for association in associations]


@router.delete(
    "/{workspace_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_workspace_document(
    workspace_id: int,
    document_id: int,
    access: WorkspaceMembership = Depends(require_workspace_role("researcher")),
    db: Session = Depends(get_db),
):
    association = (
        db.query(WorkspaceDocument)
        .filter(
            WorkspaceDocument.workspace_id == workspace_id,
            WorkspaceDocument.document_id == document_id,
        )
        .first()
    )

    if association is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace document association not found.",
        )

    db.delete(association)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
