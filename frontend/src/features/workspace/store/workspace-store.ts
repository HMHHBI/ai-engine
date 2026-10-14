import { create } from "zustand";
import type { Workspace, WorkspaceDocument } from "@/types/workspace";
import type { ResearchRun } from "@/types/research";

interface WorkspaceState {
  workspaces: Workspace[];
  activeWorkspaceId: number | null;
  documentsByWorkspace: Record<number, WorkspaceDocument[]>;
  researchRunsByWorkspace: Record<number, ResearchRun[]>;
  isLoading: boolean;
  error: string | null;

  setWorkspaces: (workspaces: Workspace[]) => void;
  setActiveWorkspaceId: (workspaceId: number | null) => void;
  setWorkspaceDocuments: (workspaceId: number, documents: WorkspaceDocument[]) => void;
  addResearchRun: (workspaceId: number, run: ResearchRun) => void;
  setResearchRuns: (workspaceId: number, runs: ResearchRun[]) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspaces: [],
  activeWorkspaceId: null,
  documentsByWorkspace: {},
  researchRunsByWorkspace: {},
  isLoading: false,
  error: null,

  setWorkspaces: (workspaces) => set({ workspaces }),
  setActiveWorkspaceId: (activeWorkspaceId) => set({ activeWorkspaceId }),
  setWorkspaceDocuments: (workspaceId, documents) =>
    set((state) => ({
      documentsByWorkspace: {
        ...state.documentsByWorkspace,
        [workspaceId]: documents,
      },
    })),
  addResearchRun: (workspaceId, run) =>
    set((state) => ({
      researchRunsByWorkspace: {
        ...state.researchRunsByWorkspace,
        [workspaceId]: [run, ...(state.researchRunsByWorkspace[workspaceId] ?? [])],
      },
    })),
  setResearchRuns: (workspaceId, runs) =>
    set((state) => ({
      researchRunsByWorkspace: {
        ...state.researchRunsByWorkspace,
        [workspaceId]: runs,
      },
    })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  reset: () =>
    set({
      workspaces: [],
      activeWorkspaceId: null,
      documentsByWorkspace: {},
      researchRunsByWorkspace: {},
      isLoading: false,
      error: null,
    }),
}));
