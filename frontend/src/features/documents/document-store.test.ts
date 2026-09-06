import { describe, it, expect, beforeEach } from "vitest";
import { useDocumentStore } from "./document-store";
import type { Document } from "@/types/api";

const mockDocA: Document = {
  id: 1,
  user_id: 1,
  chat_id: 10,
  filename: "docA.pdf",
  mime_type: "application/pdf",
  file_size: 500,
  page_count: 1,
  storage_url: null,
  status: "ready",
  error_message: null,
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
};

const mockDocB: Document = {
  id: 2,
  user_id: 1,
  chat_id: 20,
  filename: "docB.pdf",
  mime_type: "application/pdf",
  file_size: 700,
  page_count: 3,
  storage_url: null,
  status: "processing",
  error_message: null,
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
};

describe("useDocumentStore", () => {
  beforeEach(() => {
    useDocumentStore.getState().reset();
  });

  it("isolates documents by chat", () => {
    const { setDocuments } = useDocumentStore.getState();
    setDocuments(10, [mockDocA]);
    setDocuments(20, [mockDocB]);

    const state = useDocumentStore.getState();
    expect(state.documentsByChat[10]).toHaveLength(1);
    expect(state.documentsByChat[10][0].id).toBe(1);
    expect(state.documentsByChat[20]).toHaveLength(1);
    expect(state.documentsByChat[20][0].id).toBe(2);
  });

  it("adds and updates document in store", () => {
    const { addDocument, updateDocumentInStore } = useDocumentStore.getState();
    addDocument(mockDocA);

    let state = useDocumentStore.getState();
    expect(state.documentsByChat[10][0].filename).toBe("docA.pdf");

    updateDocumentInStore({ ...mockDocA, filename: "renamed.pdf" });
    state = useDocumentStore.getState();
    expect(state.documentsByChat[10][0].filename).toBe("renamed.pdf");
  });

  it("removes document and clears selection if selected", () => {
    const { setDocuments, setSelectedDocument, removeDocumentFromStore } =
      useDocumentStore.getState();
    setDocuments(10, [mockDocA]);
    setSelectedDocument(10, mockDocA.id);

    expect(useDocumentStore.getState().selectedDocumentIdByChat[10]).toBe(mockDocA.id);

    removeDocumentFromStore(10, mockDocA.id);

    const state = useDocumentStore.getState();
    expect(state.documentsByChat[10]).toHaveLength(0);
    expect(state.selectedDocumentIdByChat[10]).toBeNull();
  });

  it("tracks loading, uploading, mutating, and error states", () => {
    const { setLoading, setUploading, setDocumentMutating, setError } =
      useDocumentStore.getState();

    setLoading(10, true);
    setUploading(10, true);
    setDocumentMutating(1, true);
    setError(10, "Failed to load");

    const state = useDocumentStore.getState();
    expect(state.loadingByChat[10]).toBe(true);
    expect(state.uploadingByChat[10]).toBe(true);
    expect(state.mutatingDocumentIds[1]).toBe(true);
    expect(state.errorByChat[10]).toBe("Failed to load");
  });
});