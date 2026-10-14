import { describe, it, expect, vi, beforeEach } from "vitest";
import { workspaceActions } from "./workspace-actions";
import { workspaceService } from "../services/workspace-service";
import { useWorkspaceStore } from "../store/workspace-store";

vi.mock("../services/workspace-service", () => ({
  workspaceService: {
    listWorkspaces: vi.fn(),
    createWorkspace: vi.fn(),
    listDocuments: vi.fn(),
    createResearchRun: vi.fn(),
  },
}));

describe("workspaceActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.getState().reset();
  });

  it("loads workspaces and selects the first one if none selected", async () => {
    const mockList = [{ id: 10, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" }];
    vi.mocked(workspaceService.listWorkspaces).mockResolvedValueOnce(mockList);

    await workspaceActions.loadWorkspaces();

    const state = useWorkspaceStore.getState();
    expect(state.workspaces).toEqual(mockList);
    expect(state.activeWorkspaceId).toBe(10);
    expect(state.isLoading).toBe(false);
  });

  it("triggers research synthesis and appends to research runs store", async () => {
    const mockRun = {
      id: 99,
      workspace_id: 10,
      requester_id: 1,
      query: "Cross paper analysis",
      status: "completed" as const,
      answer: "Findings",
      citations: [],
      run_metadata: {},
      created_at: "",
      completed_at: "",
    };
    vi.mocked(workspaceService.createResearchRun).mockResolvedValueOnce(mockRun);

    const result = await workspaceActions.triggerResearchSynthesis(10, {
      query: "Cross paper analysis",
      document_ids: [1, 2],
    });

    expect(result.id).toBe(99);
    const runs = useWorkspaceStore.getState().researchRunsByWorkspace[10];
    expect(runs).toBeDefined();
    expect(runs[0].id).toBe(99);
  });
});
