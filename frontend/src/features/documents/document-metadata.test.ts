import { beforeEach, describe, expect, it, vi } from "vitest";
import { updateDocument } from "./document-actions";
import { useDocumentStore } from "./document-store";
import type { Document } from "@/types/api";

const { mockUpdate } = vi.hoisted(() => ({
  mockUpdate: vi.fn(),
}));

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    update: mockUpdate,
    delete: vi.fn(),
    listForChat: vi.fn(),
    get: vi.fn(),
  },
}));

function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: 10,
    user_id: 1,
    chat_id: 5,
    filename: "original.pdf",
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("document metadata actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("updates the document after a successful PATCH", async () => {
    const original = makeDocument();
    const updated = makeDocument({
      filename: "renamed.pdf",
      page_count: 12,
    });

    useDocumentStore.getState().setDocuments(5, [original]);
    mockUpdate.mockResolvedValue(updated);

    await updateDocument(10, {
      filename: "renamed.pdf",
      page_count: 12,
    });

    const document = useDocumentStore.getState().documentsByChat[5][0];
    expect(document.filename).toBe("renamed.pdf");
    expect(document.page_count).toBe(12);
    expect(mockUpdate).toHaveBeenCalledWith(10, {
      filename: "renamed.pdf",
      page_count: 12,
    });
  });

  it("does not mutate local state when PATCH fails", async () => {
    const original = makeDocument();
    useDocumentStore.getState().setDocuments(5, [original]);
    mockUpdate.mockRejectedValue(new Error("PATCH failed"));

    await expect(
      updateDocument(10, { filename: "renamed.pdf" }),
    ).rejects.toThrow("PATCH failed");

    const document = useDocumentStore.getState().documentsByChat[5][0];
    expect(document.filename).toBe("original.pdf");
  });

  it("always clears mutation state after PATCH failure", async () => {
    const original = makeDocument();
    useDocumentStore.getState().setDocuments(5, [original]);
    mockUpdate.mockRejectedValue(new Error("PATCH failed"));

    await expect(
      updateDocument(10, { filename: "renamed.pdf" }),
    ).rejects.toThrow();

    expect(useDocumentStore.getState().mutatingDocumentIds[10]).toBe(false);
  });
});