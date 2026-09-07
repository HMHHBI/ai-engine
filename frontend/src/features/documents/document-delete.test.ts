import { beforeEach, describe, expect, it, vi } from "vitest";
import { deleteDocument } from "./document-actions";
import { useDocumentStore } from "./document-store";
import type { Document } from "@/types/api";

const { mockDelete } = vi.hoisted(() => ({
  mockDelete: vi.fn(),
}));

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    update: vi.fn(),
    delete: mockDelete,
    listForChat: vi.fn(),
    get: vi.fn(),
  },
}));

function makeDocument(id: number, overrides: Partial<Document> = {}): Document {
  return {
    id,
    user_id: 1,
    chat_id: 5,
    filename: `${id}.pdf`,
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

describe("document deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("removes the document after successful DELETE", async () => {
    const first = makeDocument(10);
    const second = makeDocument(20);

    useDocumentStore.getState().setDocuments(5, [first, second]);
    mockDelete.mockResolvedValue(undefined);

    await deleteDocument(5, 10);

    expect(
      useDocumentStore.getState().documentsByChat[5].map((d) => d.id),
    ).toEqual([20]);
    expect(mockDelete).toHaveBeenCalledWith(10);
  });

  it("clears selection when deleting the selected document", async () => {
    const first = makeDocument(10);
    const second = makeDocument(20);

    useDocumentStore.getState().setDocuments(5, [first, second]);
    useDocumentStore.getState().setSelectedDocument(5, 10);
    mockDelete.mockResolvedValue(undefined);

    await deleteDocument(5, 10);

    expect(useDocumentStore.getState().selectedDocumentIdByChat[5]).toBeNull();
  });

  it("does not remove the document when DELETE fails", async () => {
    const document = makeDocument(10);
    useDocumentStore.getState().setDocuments(5, [document]);
    mockDelete.mockRejectedValue(new Error("DELETE failed"));

    await expect(deleteDocument(5, 10)).rejects.toThrow("DELETE failed");
    expect(useDocumentStore.getState().documentsByChat[5]).toHaveLength(1);
  });

  it("clears mutation state after DELETE failure", async () => {
    const document = makeDocument(10);
    useDocumentStore.getState().setDocuments(5, [document]);
    mockDelete.mockRejectedValue(new Error("DELETE failed"));

    await expect(deleteDocument(5, 10)).rejects.toThrow();
    expect(useDocumentStore.getState().mutatingDocumentIds[10]).toBe(false);
  });

  it("can delete the last document without affecting the chat", async () => {
    const document = makeDocument(10);
    useDocumentStore.getState().setDocuments(5, [document]);
    mockDelete.mockResolvedValue(undefined);

    await deleteDocument(5, 10);

    expect(useDocumentStore.getState().documentsByChat[5]).toEqual([]);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[5]).toBeNull();
  });
});