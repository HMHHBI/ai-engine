import { apiClient } from "@/lib/api/client";
import type {
  Workspace,
  WorkspaceMember,
  WorkspaceDocument,
  WorkspaceRole,
} from "@/types/workspace";
import type {
  ResearchRun,
  CreateResearchRunInput,
} from "@/types/research";

export type ResearchExportFormat = "markdown" | "json";

export interface ResearchExportResponse {
  contentType: string;
  filename: string;
  content: string | Record<string, unknown>;
}

export const workspaceService = {
  // --- Workspace CRUD ---
  async listWorkspaces(): Promise<Workspace[]> {
    return apiClient.get<Workspace[]>("/workspaces");
  },

  async getWorkspace(workspaceId: number): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${workspaceId}`);
  },

  async createWorkspace(name: string): Promise<Workspace> {
    return apiClient.post<Workspace>("/workspaces", { name });
  },

  async updateWorkspace(workspaceId: number, name: string): Promise<Workspace> {
    return apiClient.patch<Workspace>(`/workspaces/${workspaceId}`, { name });
  },

  async deleteWorkspace(workspaceId: number): Promise<void> {
    await apiClient.delete(`/workspaces/${workspaceId}`);
  },

  // --- Members ---
  async inviteMember(
    workspaceId: number,
    email: string,
    role: WorkspaceRole = "researcher",
  ): Promise<WorkspaceMember> {
    return apiClient.post<WorkspaceMember>(`/workspaces/${workspaceId}/members`, {
      email,
      role,
    });
  },

  async updateMemberRole(
    workspaceId: number,
    userId: number,
    role: WorkspaceRole,
  ): Promise<WorkspaceMember> {
    return apiClient.patch<WorkspaceMember>(
      `/workspaces/${workspaceId}/members/${userId}`,
      { role },
    );
  },

  async removeMember(workspaceId: number, userId: number): Promise<void> {
    await apiClient.delete(`/workspaces/${workspaceId}/members/${userId}`);
  },

  // --- Documents ---
  async listDocuments(workspaceId: number): Promise<WorkspaceDocument[]> {
    return apiClient.get<WorkspaceDocument[]>(`/workspaces/${workspaceId}/documents`);
  },

  async attachDocuments(
    workspaceId: number,
    documentIds: number[],
  ): Promise<WorkspaceDocument[]> {
    return apiClient.post<WorkspaceDocument[]>(
      `/workspaces/${workspaceId}/documents`,
      { document_ids: documentIds },
    );
  },

  async detachDocument(workspaceId: number, documentId: number): Promise<void> {
    await apiClient.delete(`/workspaces/${workspaceId}/documents/${documentId}`);
  },

  // --- Research Runs & Synthesis ---
  async createResearchRun(
    workspaceId: number,
    payload: CreateResearchRunInput,
  ): Promise<ResearchRun> {
    return apiClient.post<ResearchRun>(
      `/workspaces/${workspaceId}/research/runs`,
      payload,
    );
  },

  async getResearchRun(
    workspaceId: number,
    runId: number,
  ): Promise<ResearchRun> {
    return apiClient.get<ResearchRun>(
      `/workspaces/${workspaceId}/research/runs/${runId}`,
    );
  },

  async downloadResearchExport(
    workspaceId: number,
    runId: number,
    format: ResearchExportFormat = "markdown",
  ): Promise<void> {
    const rawUrl = `${(process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")}/workspaces/${workspaceId}/research/runs/${runId}/export?format=${format}`;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

    const response = await fetch(rawUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      throw new Error(`Export download failed with status ${response.status}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `research-run-${runId}.${format === "json" ? "json" : "md"}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },
};
