import { workspaceService } from "../services/workspace-service";
import { useWorkspaceStore } from "../store/workspace-store";
import { apiClient } from "@/lib/api/client";
import type { CreateResearchRunInput, ResearchRun } from "@/types/research";
import type { WorkspaceDocument } from "@/types/workspace";
import type { Document as ApiDocument } from "@/types/api";

const latestDocRequestByWorkspace = new Map<number, number>();
const inFlightDocWorkspaces = new Set<number>();
const latestRunsRequestByWorkspace = new Map<number, number>();
let latestWorkspacesRequestSeq = 0;
let activeLoadingOperations = 0;

function beginLoading(): void {
  activeLoadingOperations += 1;
  useWorkspaceStore.getState().setLoading(true);
}

function endLoading(): void {
  activeLoadingOperations = Math.max(0, activeLoadingOperations - 1);
  if (activeLoadingOperations === 0) {
    useWorkspaceStore.getState().setLoading(false);
  }
}

export const workspaceActions = {
  async loadWorkspaces(): Promise<void> {
    const requestId = ++latestWorkspacesRequestSeq;
    const store = useWorkspaceStore.getState();
    beginLoading();
    store.setError(null);
    try {
      const list = await workspaceService.listWorkspaces();
      if (latestWorkspacesRequestSeq !== requestId) {
        return;
      }
      store.setWorkspaces(list);

      const currentActiveId = useWorkspaceStore.getState().activeWorkspaceId;
      const isCurrentValid = list.some((ws) => ws.id === currentActiveId);

      if (!isCurrentValid) {
        const nextId = list.length > 0 ? list[0].id : null;
        store.setActiveWorkspaceId(nextId);
        if (nextId !== null && !inFlightDocWorkspaces.has(nextId)) {
          void this.loadDocuments(nextId);
        }
      } else if (currentActiveId !== null && !inFlightDocWorkspaces.has(currentActiveId)) {
        void this.loadDocuments(currentActiveId);
      }
    } catch (err) {
      if (latestWorkspacesRequestSeq === requestId) {
        store.setError(err instanceof Error ? err.message : "Failed to load workspaces.");
      }
    } finally {
      endLoading();
    }
  },

  async selectWorkspace(workspaceId: number): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setError(null);
    store.setActiveWorkspaceId(workspaceId);
    beginLoading();

    try {
      await Promise.all([
        this.loadDocuments(workspaceId),
        this.loadResearchRuns(workspaceId),
      ]);
    } finally {
      endLoading();
    }
  },

  async loadDocuments(workspaceId: number): Promise<void> {
    const requestId = (latestDocRequestByWorkspace.get(workspaceId) ?? 0) + 1;
    latestDocRequestByWorkspace.set(workspaceId, requestId);
    inFlightDocWorkspaces.add(workspaceId);

    try {
      const docs = await workspaceService.listDocuments(workspaceId);
      if (latestDocRequestByWorkspace.get(workspaceId) !== requestId) {
        return;
      }
      useWorkspaceStore.getState().setWorkspaceDocuments(workspaceId, docs);
    } catch (err) {
      console.warn("loadDocuments warning:", err);
    } finally {
      if (latestDocRequestByWorkspace.get(workspaceId) === requestId) {
        inFlightDocWorkspaces.delete(workspaceId);
      }
    }
  },

  async fetchAvailableDocuments(): Promise<ApiDocument[]> {
    return await apiClient.get<ApiDocument[]>("/documents");
  },

  async attachDocuments(workspaceId: number, documentIds: number[]): Promise<void> {
    const store = useWorkspaceStore.getState();
    beginLoading();
    store.setError(null);
    try {
      const updated = await workspaceService.attachDocuments(workspaceId, documentIds);
      store.setWorkspaceDocuments(workspaceId, updated);
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Failed to attach documents.");
      throw err;
    } finally {
      endLoading();
    }
  },

  async detachDocument(workspaceId: number, documentId: number): Promise<void> {
    const store = useWorkspaceStore.getState();
    beginLoading();
    store.setError(null);
    try {
      await workspaceService.detachDocument(workspaceId, documentId);
      const current = store.documentsByWorkspace[workspaceId] ?? [];
      store.setWorkspaceDocuments(
        workspaceId,
        current.filter((d: WorkspaceDocument) => d.document_id !== documentId),
      );
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Failed to detach document.");
      throw err;
    } finally {
      endLoading();
    }
  },

  async createWorkspace(name: string): Promise<number | null> {
    const store = useWorkspaceStore.getState();
    beginLoading();
    store.setError(null);
    try {
      const workspace = await workspaceService.createWorkspace(name);
      await this.loadWorkspaces();
      store.setActiveWorkspaceId(workspace.id);
      return workspace.id;
    } catch (err) {
      store.setError(
        err instanceof Error ? err.message : "Failed to create workspace.",
      );
      return null;
    } finally {
      endLoading();
    }
  },

  async loadResearchRuns(workspaceId: number): Promise<void> {
    const requestId = (latestRunsRequestByWorkspace.get(workspaceId) ?? 0) + 1;
    latestRunsRequestByWorkspace.set(workspaceId, requestId);

    const store = useWorkspaceStore.getState();
    try {
      const response = await workspaceService.listResearchRuns(workspaceId);
      if (latestRunsRequestByWorkspace.get(workspaceId) !== requestId) {
        return;
      }
      store.setResearchRuns(workspaceId, response.items || []);
    } catch {
      // Do not crash UI on history fetch error
    }
  },

  async refreshResearchRun(
    workspaceId: number,
    runId: number,
  ): Promise<ResearchRun | null> {
    try {
      const updated = await workspaceService.getResearchRun(workspaceId, runId);
      useWorkspaceStore.getState().addResearchRun(workspaceId, updated);
      return updated;
    } catch {
      return null;
    }
  },

  async triggerResearchSynthesis(
    workspaceId: number,
    input: CreateResearchRunInput,
  ) {
    const store = useWorkspaceStore.getState();
    beginLoading();
    store.setError(null);
    try {
      const run = await workspaceService.createResearchRun(workspaceId, input, { asyncMode: true });
      store.addResearchRun(workspaceId, run);
      return run;
    } catch (err) {
      throw err;
    } finally {
      endLoading();
    }
  },

  async cancelResearchRun(workspaceId: number, runId: number) {
    const response = await workspaceService.cancelResearchRun(workspaceId, runId);
    const refreshed = await this.refreshResearchRun(workspaceId, runId);
    return { response, run: refreshed };
  },
};
