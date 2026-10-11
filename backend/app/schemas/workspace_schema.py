from __future__ import annotations
import enum
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class WorkspaceMembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class WorkspaceMemberInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    role: WorkspaceRole = WorkspaceRole.RESEARCHER


class WorkspaceMemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: WorkspaceRole


class WorkspaceMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workspace_id: int
    user_id: int
    user_email: str
    user_name: str
    role: WorkspaceRole
    status: WorkspaceMembershipStatus
    created_at: datetime
    updated_at: datetime


class WorkspaceDocumentAttach(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[int] = Field(min_length=1, max_length=50)


class WorkspaceDocumentOut(BaseModel):
    document_id: int
    chat_id: int | None = None
    filename: str
    mime_type: str
    status: str
    added_by: int
    added_at: datetime
