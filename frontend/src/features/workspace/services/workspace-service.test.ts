import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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

  it("lists workspaces using canonical collection endpoint GET /workspaces/", async () => {
    const mockList = [{ id: 1, name: "AI Lab", created_by: 10, created_at: "", updated_at: "" }];
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockList);

    const result = await workspaceService.listWorkspaces();
    expect(apiClient.get).toHaveBeenCalledWith("/workspaces/");
    expect(result).toEqual(mockList);
  });

  it("creates workspace using canonical collection endpoint POST /workspaces/", async () => {
    const mockWs = { id: 2, name: "New Lab", created_by: 10, created_at: "", updated_at: "" };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockWs);

    const result = await workspaceService.createWorkspace("New Lab");
    expect(apiClient.post).toHaveBeenCalledWith("/workspaces/", { name: "New Lab" });
    expect(result).toEqual(mockWs);
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

  describe("downloadResearchExport", () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
      vi.useFakeTimers();
      window.URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
      window.URL.revokeObjectURL = vi.fn();
    });

    afterEach(() => {
      global.fetch = originalFetch;
      vi.useRealTimers();
      localStorage.clear();
    });

    it("downloads markdown export with auth token and deferred cleanup", async () => {
      localStorage.setItem("token", "fake-token-123");
      const mockBlob = new Blob(["# Research Run 10"], { type: "text/markdown" });

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => mockBlob,
      });

      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

      await workspaceService.downloadResearchExport(1, 10, "markdown");

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/workspaces/1/research/runs/10/export?format=markdown"),
        {
          headers: { Authorization: "Bearer fake-token-123" },
        },
      );
      expect(window.URL.createObjectURL).toHaveBeenCalledWith(mockBlob);
      expect(clickSpy).toHaveBeenCalledTimes(1);

      // Deferred revocation check
      expect(window.URL.revokeObjectURL).not.toHaveBeenCalled();
      vi.advanceTimersByTime(150);
      expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");

      clickSpy.mockRestore();
    });

    it("throws an error when export download response is not ok", async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(
        workspaceService.downloadResearchExport(1, 99, "json"),
      ).rejects.toThrow("Export download failed with status 404");
    });
  });

  describe("streamResearchRunEvents", () => {
    it("parses CRLF and fragmented SSE frames and fires onClose when stream ends before done", async () => {
      const encoder = new TextEncoder();
      const chunks = [
        encoder.encode('event: stage\r\ndata: {"run_id":7,"workspace_id":2,'),
        encoder.encode('"status":"retrieving","stage":"retrieving","progress_percent":40,"cancel_requested":false,"attempt_count":1,"updated_at":"2026-11-25T10:00:00Z"}\r\n\r\n'),
      ];
      let idx = 0;

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => {
              if (idx < chunks.length) {
                return { done: false, value: chunks[idx++] };
              }
              return { done: true, value: undefined };
            },
          }),
        },
      });

      const stages: number[] = [];
      const onDone = vi.fn();
      const onClose = vi.fn();

      workspaceService.streamResearchRunEvents(2, 7, {
        onStage: (evt) => stages.push(evt.progress_percent),
        onDone,
        onClose,
      });

      await vi.waitFor(() => {
        expect(stages).toEqual([40]);
        expect(onClose).toHaveBeenCalledTimes(1);
      });
      expect(onDone).not.toHaveBeenCalled();
    });
  });
});
