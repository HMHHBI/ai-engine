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
  ResearchRunCancelResponse,
  ResearchRunStageEvent,
} from "@/types/research";

export type ResearchExportFormat = "markdown" | "json";

export const workspaceService = {
  // --- Workspace CRUD ---
  async listWorkspaces(): Promise<Workspace[]> {
    return apiClient.get<Workspace[]>("/workspaces/");
  },

  async getWorkspace(workspaceId: number): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${workspaceId}`);
  },

  async createWorkspace(name: string): Promise<Workspace> {
    return apiClient.post<Workspace>("/workspaces/", { name });
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
    options?: { asyncMode?: boolean },
  ): Promise<ResearchRun> {
    const suffix = options?.asyncMode ? "?async_mode=true" : "";
    return apiClient.post<ResearchRun>(
      `/workspaces/${workspaceId}/research/runs${suffix}`,
      payload,
    );
  },

  async listResearchRuns(
    workspaceId: number,
    offset: number = 0,
    limit: number = 50,
  ): Promise<{ items: ResearchRun[]; total: number }> {
    return apiClient.get<{ items: ResearchRun[]; total: number }>(
      `/workspaces/${workspaceId}/research/runs?offset=${offset}&limit=${limit}`,
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

  async cancelResearchRun(
    workspaceId: number,
    runId: number,
  ): Promise<ResearchRunCancelResponse> {
    return apiClient.post<ResearchRunCancelResponse>(
      `/workspaces/${workspaceId}/research/runs/${runId}/cancel`,
      {},
    );
  },

  streamResearchRunEvents(
    workspaceId: number,
    runId: number,
    handlers: {
      onStage: (event: ResearchRunStageEvent) => void;
      onDone: (event: ResearchRunStageEvent) => void;
      onError?: (err: unknown) => void;
    },
  ): () => void {
    const controller = new AbortController();
    const baseUrl = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    const url = `${baseUrl}/workspaces/${workspaceId}/research/runs/${runId}/events`;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

    void (async () => {
      try {
        const response = await fetch(url, {
          headers: {
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE stream failed with status ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            const lines = frame.split("\n");
            let eventType = "message";
            let dataStr = "";
            for (const line of lines) {
              if (line.startsWith("event:")) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                dataStr += line.slice(5).trim();
              }
            }
            if (!dataStr) continue;
            const parsed = JSON.parse(dataStr) as ResearchRunStageEvent;
            if (eventType === "done") {
              handlers.onDone(parsed);
            } else if (eventType === "stage") {
              handlers.onStage(parsed);
            }
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          handlers.onError?.(err);
        }
      }
    })();

    return () => {
      controller.abort();
    };
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
    setTimeout(() => {
      window.URL.revokeObjectURL(downloadUrl);
    }, 100);
  },
};
