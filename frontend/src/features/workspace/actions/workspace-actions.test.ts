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

  it("reconciles stale activeWorkspaceId to the first available workspace", async () => {
    // Current state has a stale workspace id 999 from previous user session
    useWorkspaceStore.setState({ activeWorkspaceId: 999 });

    const mockList = [{ id: 10, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" }];
    vi.mocked(workspaceService.listWorkspaces).mockResolvedValueOnce(mockList);

    await workspaceActions.loadWorkspaces();

    const state = useWorkspaceStore.getState();
    expect(state.workspaces).toEqual(mockList);
    // 999 was not in list, so it reconciled to 10
    expect(state.activeWorkspaceId).toBe(10);
    expect(state.isLoading).toBe(false);
  });

  it("preserves activeWorkspaceId if it exists in the fetched list", async () => {
    useWorkspaceStore.setState({ activeWorkspaceId: 20 });

    const mockList = [
      { id: 10, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
      { id: 20, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
    ];
    vi.mocked(workspaceService.listWorkspaces).mockResolvedValueOnce(mockList);

    await workspaceActions.loadWorkspaces();

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(20);
  });
});
