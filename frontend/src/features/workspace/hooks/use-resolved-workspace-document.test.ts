import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useResolvedWorkspaceDocument } from "./use-resolved-workspace-document";
import { documentApi } from "@/lib/api/documents";
import type { Document } from "@/types/api";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    get: vi.fn(),
  },
}));

describe("useResolvedWorkspaceDocument (M4.3 & Hardening)", () => {
  const mockDoc101: Document = {
    id: 101,
    user_id: 1,
    chat_id: 1,
    filename: "sample101.pdf",
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };

  const mockDoc202: Document = {
    id: 202,
    user_id: 1,
    chat_id: 1,
    filename: "sample202.pdf",
    mime_type: "application/pdf",
    file_size: 2048,
    page_count: 10,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns idle status when candidateDocId is null", () => {
    const { result } = renderHook(() => useResolvedWorkspaceDocument(null));
    expect(result.current.status).toBe("idle");
    expect(result.current.document).toBeNull();
    expect(result.current.error).toBeNull();
    expect(documentApi.get).not.toHaveBeenCalled();
  });

  it("resolves document successfully on HTTP 200", async () => {
    vi.mocked(documentApi.get).mockResolvedValueOnce(mockDoc101);

    const { result } = renderHook(() => useResolvedWorkspaceDocument(101));
    expect(result.current.status).toBe("loading");

    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
    });

    expect(result.current.document).toEqual(mockDoc101);
    expect(result.current.error).toBeNull();
    expect(documentApi.get).toHaveBeenCalledWith(101);
  });

  it("handles not_found when API returns 404 or 403", async () => {
    vi.mocked(documentApi.get).mockRejectedValueOnce({ status: 404 });

    const { result } = renderHook(() => useResolvedWorkspaceDocument(999));

    await waitFor(() => {
      expect(result.current.status).toBe("not_found");
    });

    expect(result.current.document).toBeNull();
    expect(result.current.error).toContain("Document not found");
  });

  it("handles generic API errors with error status", async () => {
    vi.mocked(documentApi.get).mockRejectedValueOnce(new Error("Network connection lost"));

    const { result } = renderHook(() => useResolvedWorkspaceDocument(101));

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });

    expect(result.current.document).toBeNull();
    expect(result.current.error).toBe("Network connection lost");
  });

  it("prevents stale document exposure during candidate switch 101 -> 202", async () => {
    vi.mocked(documentApi.get).mockImplementation(async (id: number) => {
      if (id === 101) return mockDoc101;
      if (id === 202) return mockDoc202;
      throw { status: 404 };
    });

    let currentCandidate: number | null = 101;
    const { result, rerender } = renderHook(() => useResolvedWorkspaceDocument(currentCandidate));

    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
      expect(result.current.document?.id).toBe(101);
    });

    // Switch candidate to 202
    currentCandidate = 202;
    rerender();

    // Invariant: MUST NOT expose document 101
    expect(result.current.status).toBe("loading");
    expect(result.current.document).toBeNull();

    // Eventually resolves to 202
    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
      expect(result.current.document?.id).toBe(202);
    });
  });

  it("synchronously clears resolved state when candidate becomes null", async () => {
    vi.mocked(documentApi.get).mockResolvedValueOnce(mockDoc101);

    let currentCandidate: number | null = 101;
    const { result, rerender } = renderHook(() => useResolvedWorkspaceDocument(currentCandidate));

    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
      expect(result.current.document?.id).toBe(101);
    });

    currentCandidate = null;
    rerender();

    expect(result.current.status).toBe("idle");
    expect(result.current.document).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
