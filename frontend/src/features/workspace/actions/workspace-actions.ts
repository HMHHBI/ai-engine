import { workspaceService } from "../services/workspace-service";
import { useWorkspaceStore } from "../store/workspace-store";
import { apiClient } from "@/lib/api/client";
import type { CreateResearchRunInput } from "@/types/research";
import type { WorkspaceDocument } from "@/types/workspace";
import type { Document as ApiDocument } from "@/types/api";

const latestDocRequestByWorkspace = new Map<number, number>();
const latestRunsRequestByWorkspace = new Map<number, number>();
let workspaceSelectionSeq = 0;

export const workspaceActions = {
  async loadWorkspaces(): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const list = await workspaceService.listWorkspaces();
      store.setWorkspaces(list);

      const currentActiveId = useWorkspaceStore.getState().activeWorkspaceId;
      const isCurrentValid = list.some((ws) => ws.id === currentActiveId);

      if (!isCurrentValid) {
        const nextId = list.length > 0 ? list[0].id : null;
        store.setActiveWorkspaceId(nextId);
        if (nextId !== null) {
          void this.loadDocuments(nextId);
        }
      } else if (currentActiveId !== null) {
        void this.loadDocuments(currentActiveId);
      }
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Failed to load workspaces.");
    } finally {
      store.setLoading(false);
    }
  },

  async selectWorkspace(workspaceId: number): Promise<void> {
    const selectionToken = ++workspaceSelectionSeq;
    const store = useWorkspaceStore.getState();
    store.setError(null);
    store.setActiveWorkspaceId(workspaceId);
    store.setLoading(true);

    try {
      await Promise.all([
        this.loadDocuments(workspaceId),
        this.loadResearchRuns(workspaceId),
      ]);
    } finally {
      if (workspaceSelectionSeq === selectionToken) {
        useWorkspaceStore.getState().setLoading(false);
      }
    }
  },

  async loadDocuments(workspaceId: number): Promise<void> {
    const requestId = (latestDocRequestByWorkspace.get(workspaceId) ?? 0) + 1;
    latestDocRequestByWorkspace.set(workspaceId, requestId);

    try {
      const docs = await workspaceService.listDocuments(workspaceId);
      if (latestDocRequestByWorkspace.get(workspaceId) !== requestId) {
        return;
      }
      useWorkspaceStore.getState().setWorkspaceDocuments(workspaceId, docs);
    } catch (err) {
      // Do not pollute global store error to prevent cascading re-render loops
      console.warn("loadDocuments warning:", err);
    }
  },

  async fetchAvailableDocuments(): Promise<ApiDocument[]> {
    return await apiClient.get<ApiDocument[]>("/documents");
  },

  async attachDocuments(workspaceId: number, documentIds: number[]): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const updated = await workspaceService.attachDocuments(workspaceId, documentIds);
      store.setWorkspaceDocuments(workspaceId, updated);
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Failed to attach documents.");
      throw err;
    } finally {
      store.setLoading(false);
    }
  },

  async detachDocument(workspaceId: number, documentId: number): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
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
      store.setLoading(false);
    }
  },

  async createWorkspace(name: string): Promise<number | null> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
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
      store.setLoading(false);
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

  async triggerResearchSynthesis(
    workspaceId: number,
    input: CreateResearchRunInput,
  ) {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const run = await workspaceService.createResearchRun(workspaceId, input);
      store.addResearchRun(workspaceId, run);
      return run;
    } catch (err) {
      // Do not corrupt global store error; allow caller to handle local UI state
      throw err;
    } finally {
      store.setLoading(false);
    }
  },
};
