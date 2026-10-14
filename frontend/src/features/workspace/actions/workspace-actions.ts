import { workspaceService } from "../services/workspace-service";
import { useWorkspaceStore } from "../store/workspace-store";
import type { CreateResearchRunInput } from "@/types/research";

export const workspaceActions = {
  async loadWorkspaces(): Promise<void> {
    const store = useWorkspaceStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const list = await workspaceService.listWorkspaces();
      store.setWorkspaces(list);
      if (list.length > 0 && store.activeWorkspaceId === null) {
        store.setActiveWorkspaceId(list[0].id);
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
      useWorkspaceStore.getState().setError(
        err instanceof Error ? err.message : "Failed to load workspace documents.",
      );
    }
  },

  async createWorkspace(name: string): Promise<number | null> {
    try {
      const workspace = await workspaceService.createWorkspace(name);
      await this.loadWorkspaces();
      useWorkspaceStore.getState().setActiveWorkspaceId(workspace.id);
      return workspace.id;
    } catch (err) {
      useWorkspaceStore.getState().setError(
        err instanceof Error ? err.message : "Failed to create workspace.",
      );
      return null;
    }
  },

  async triggerResearchSynthesis(
    workspaceId: number,
    input: CreateResearchRunInput,
  ) {
    try {
      const run = await workspaceService.createResearchRun(workspaceId, input);
      useWorkspaceStore.getState().addResearchRun(workspaceId, run);
      return run;
    } catch (err) {
      useWorkspaceStore.getState().setError(
        err instanceof Error ? err.message : "Failed to trigger research synthesis.",
      );
      throw err;
    }
  },
};
