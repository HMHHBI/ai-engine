import { workspaceService } from "../services/workspace-service";
import { useWorkspaceStore } from "../store/workspace-store";
import { apiClient } from "@/lib/api/client";
import type { CreateResearchRunInput } from "@/types/research";
import type { WorkspaceDocument } from "@/types/workspace";
import type { Document as ApiDocument } from "@/types/api";

export const workspaceActions = {
  async loadWorkspaces(): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const list = await workspaceService.listWorkspaces();
      store.setWorkspaces(list);

      const currentActiveId = store.activeWorkspaceId;
      const isCurrentValid = list.some((ws) => ws.id === currentActiveId);

      if (!isCurrentValid) {
        const nextId = list.length > 0 ? list[0].id : null;
        store.setActiveWorkspaceId(nextId);
        if (nextId) {
          void this.loadDocuments(nextId);
        }
      } else if (currentActiveId) {
        void this.loadDocuments(currentActiveId);
      }
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Failed to load workspaces.");
    } finally {
      store.setLoading(false);
    }
  },

  async selectWorkspace(workspaceId: number): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setActiveWorkspaceId(workspaceId);
    await this.loadDocuments(workspaceId);
  },

  async loadDocuments(workspaceId: number): Promise<void> {
    try {
      const docs = await workspaceService.listDocuments(workspaceId);
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
    const store = useWorkspaceStore.getState();
    try {
      const response = await workspaceService.listResearchRuns(workspaceId);
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
