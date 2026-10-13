from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User, WorkspaceMembership
from app.db.session import get_db

ROLE_LEVELS = {
    "viewer": 1,
    "researcher": 2,
    "admin": 3,
    "owner": 4,
}


def require_workspace_role(minimum_role: str):
    if minimum_role not in ROLE_LEVELS:
        raise ValueError(f"Unknown workspace role: {minimum_role}")

    def dependency(
        workspace_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceMembership:
        membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == current_user.id,
                WorkspaceMembership.status == "active",
            )
            .first()
        )

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        actual_level = ROLE_LEVELS.get(membership.role, 0)
        required_level = ROLE_LEVELS[minimum_role]

        if actual_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient workspace permissions.",
            )

        return membership

    return dependency
