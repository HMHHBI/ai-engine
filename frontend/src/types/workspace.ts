export type WorkspaceRole = "owner" | "admin" | "researcher" | "viewer";
export type WorkspaceMembershipStatus = "active" | "invited";

export interface Workspace {
  id: number;
  name: string;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMember {
  id: number;
  workspace_id: number;
  user_id: number;
  user_email: string;
  user_name: string;
  role: WorkspaceRole;
  status: WorkspaceMembershipStatus;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceDocument {
  document_id: number;
  chat_id: number | null;
  filename: string;
  mime_type: string;
  status: string;
  added_by: number;
  added_at: string;
}
