import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useResolvedWorkspaceDocument } from "./use-resolved-workspace-document";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";
import { documentApi } from "@/lib/api/documents";
import type { Document } from "@/types/api";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    get: vi.fn(),
  },
}));

const createDoc = (id: number, chatId: number, status = "ready"): Document => ({
  id,
  user_id: 1,
  chat_id: chatId,
  filename: `doc-${id}.pdf`,
  status: status as Document["status"],
  page_count: 10,
  mime_type: "application/pdf",
  file_size: 1024,
  storage_url: `https://example.com/doc-${id}.pdf`,
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

describe("useResolvedWorkspaceDocument", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.getState().reset();
    useDocumentStore.getState().reset();
  });

  it("returns idle status when no candidateDocId or activeChatId is set", () => {
    const { result } = renderHook(() => useResolvedWorkspaceDocument(null));
    expect(result.current.status).toBe("idle");
    expect(result.current.document).toBeNull();
  });

  it("immediately resolves document if already present in memory cache", () => {
    useChatStore.setState({ activeChatId: 1 });
    const doc = createDoc(10, 1);
    useDocumentStore.setState({
      documentsByChat: { 1: [doc] },
    });

    const { result } = renderHook(() => useResolvedWorkspaceDocument(10));
    expect(result.current.status).toBe("resolved");
    expect(result.current.document?.id).toBe(10);
  });

  it("fetches uncached document from API and resolves when valid and ready", async () => {
    useChatStore.setState({ activeChatId: 1 });
    const uncachedDoc = createDoc(88, 1, "ready");
    vi.mocked(documentApi.get).mockResolvedValueOnce(uncachedDoc);

    const { result } = renderHook(() => useResolvedWorkspaceDocument(88));

    await waitFor(() => {
      expect(result.current.status).toBe("resolved");
    });

    expect(result.current.document?.id).toBe(88);
    expect(documentApi.get).toHaveBeenCalledWith(88, expect.any(Object));
    // Verify document was cached in documentStore
    expect(useDocumentStore.getState().documentsByChat[1]).toContainEqual(uncachedDoc);
  });

  it("returns not_found when fetched document belongs to another chat session", async () => {
    useChatStore.setState({ activeChatId: 1 });
    const foreignDoc = createDoc(99, 2, "ready"); // belongs to chat 2
    vi.mocked(documentApi.get).mockResolvedValueOnce(foreignDoc);

    const { result } = renderHook(() => useResolvedWorkspaceDocument(99));

    await waitFor(() => {
      expect(result.current.status).toBe("not_found");
    });
    expect(result.current.document).toBeNull();
  });

  it("returns error status when API fetch fails", async () => {
    useChatStore.setState({ activeChatId: 1 });
    vi.mocked(documentApi.get).mockRejectedValueOnce(new Error("Server error"));

    const { result } = renderHook(() => useResolvedWorkspaceDocument(44));

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });
    expect(result.current.error).toBe("Server error");
  });
});
