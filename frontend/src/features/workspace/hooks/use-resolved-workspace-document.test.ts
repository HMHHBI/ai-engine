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

describe("useResolvedWorkspaceDocument (M4.3)", () => {
  const mockDoc: Document = {
    id: 101,
    user_id: 1,
    chat_id: 1,
    filename: "sample.pdf",
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
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
    vi.mocked(documentApi.get).mockResolvedValueOnce(mockDoc);

    const { result } = renderHook(() => useResolvedWorkspaceDocument(101));
    expect(result.current.status).toBe("loading");

    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
    });

    expect(result.current.document).toEqual(mockDoc);
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
});
