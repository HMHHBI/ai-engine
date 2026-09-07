import { describe, it, expect, vi, beforeEach } from "vitest";
import { uploadDocument, validatePdfFile } from "./document-actions";
import { chatApi } from "@/lib/api/chat";
import { documentApi } from "@/lib/api/documents";
import { useDocumentStore } from "./document-store";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    uploadPdf: vi.fn(),
  },
}));

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    listForChat: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("document-upload-actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("validates PDF files correctly", () => {
    const valid = new File(["data"], "doc.pdf", { type: "application/pdf" });
    expect(validatePdfFile(valid).valid).toBe(true);

    const nonPdf = new File(["data"], "doc.png", { type: "image/png" });
    expect(validatePdfFile(nonPdf).valid).toBe(false);

    const empty = new File([], "empty.pdf", { type: "application/pdf" });
    expect(validatePdfFile(empty).valid).toBe(false);
  });

  it("uploads PDF and refreshes authoritative documents list", async () => {
    const file = new File(["%PDF-1.4 sample"], "sample.pdf", {
      type: "application/pdf",
    });

    vi.mocked(chatApi.uploadPdf).mockResolvedValueOnce({
      filename: "sample.pdf",
      chunks_total: 1,
      chunks_indexed: 1,
      chunks_failed: 0,
      embedding_provider: "test",
      message: "Indexed",
      document: {
        id: 99,
        chat_id: 1,
        filename: "sample.pdf",
        mime_type: "application/pdf",
        file_size: 100,
        page_count: 1,
        status: "ready",
      },
    } as unknown as Awaited<ReturnType<typeof chatApi.uploadPdf>>);

    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([
      {
        id: 99,
        user_id: 1,
        chat_id: 1,
        filename: "sample.pdf",
        mime_type: "application/pdf",
        file_size: 100,
        page_count: 1,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: "2026-09-06T00:00:00Z",
        updated_at: "2026-09-06T00:00:00Z",
      },
    ]);

    await uploadDocument(1, file);

    const state = useDocumentStore.getState();
    expect(state.documentsByChat[1]).toHaveLength(1);
    expect(state.documentsByChat[1][0].id).toBe(99);
    expect(state.uploadingByChat[1]).toBe(false);
  });

  it("prevents concurrent upload on same chat", async () => {
    useDocumentStore.getState().setUploading(1, true);

    const file = new File(["sample"], "sample.pdf", { type: "application/pdf" });
    await expect(uploadDocument(1, file)).rejects.toThrow(
      "An upload is already in progress for this chat."
    );
  });

  it("maintains chat isolation during upload", async () => {
    const file = new File(["data"], "chat1.pdf", { type: "application/pdf" });

    vi.mocked(chatApi.uploadPdf).mockResolvedValueOnce(
      {} as unknown as Awaited<ReturnType<typeof chatApi.uploadPdf>>
    );
    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([
      {
        id: 101,
        user_id: 1,
        chat_id: 1,
        filename: "chat1.pdf",
        mime_type: "application/pdf",
        file_size: 100,
        page_count: 1,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: "2026-09-06T00:00:00Z",
        updated_at: "2026-09-06T00:00:00Z",
      },
    ]);

    useDocumentStore.getState().setDocuments(2, [
      {
        id: 202,
        user_id: 1,
        chat_id: 2,
        filename: "chat2.pdf",
        mime_type: "application/pdf",
        file_size: 200,
        page_count: 2,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: "2026-09-06T00:00:00Z",
        updated_at: "2026-09-06T00:00:00Z",
      },
    ]);

    await uploadDocument(1, file);

    const state = useDocumentStore.getState();
    expect(state.documentsByChat[1][0].id).toBe(101);
    expect(state.documentsByChat[2][0].id).toBe(202);
  });
});