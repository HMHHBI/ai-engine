import { describe, it, expect, vi, beforeEach } from "vitest";
import { workspaceService } from "./workspace-service";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("workspaceService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists workspaces using GET /workspaces", async () => {
    const mockList = [{ id: 1, name: "AI Lab", created_by: 10, created_at: "", updated_at: "" }];
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockList);

    const result = await workspaceService.listWorkspaces();
    expect(apiClient.get).toHaveBeenCalledWith("/workspaces");
    expect(result).toEqual(mockList);
  });

  it("creates research runs using POST /workspaces/:id/research/runs", async () => {
    const mockRun = {
      id: 42,
      workspace_id: 1,
      requester_id: 10,
      query: "Analyze methodology",
      status: "completed",
      answer: "Synthetic analysis",
      citations: [],
      run_metadata: {},
      created_at: "",
      completed_at: "",
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockRun);

    const result = await workspaceService.createResearchRun(1, {
      query: "Analyze methodology",
      document_ids: [101, 102],
    });

    expect(apiClient.post).toHaveBeenCalledWith("/workspaces/1/research/runs", {
      query: "Analyze methodology",
      document_ids: [101, 102],
    });
    expect(result.id).toBe(42);
  });

  it("attaches documents using POST /workspaces/:id/documents", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce([]);

    await workspaceService.attachDocuments(5, [1, 2]);
    expect(apiClient.post).toHaveBeenCalledWith("/workspaces/5/documents", {
      document_ids: [1, 2],
    });
  });
});
