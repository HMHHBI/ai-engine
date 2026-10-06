import { describe, it, expect, vi, beforeEach } from "vitest";
import { uploadDocument, validatePdfFile } from "./document-actions";
import { documentApi } from "@/lib/api/documents";
import { useDocumentStore } from "./document-store";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    listForChat: vi.fn(),
    upload: vi.fn((chatId: number, file: File) =>
      Promise.resolve({
        id: 1,
        user_id: 1,
        chat_id: chatId,
        filename: file.name,
        mime_type: file.type || "application/pdf",
        file_size: file.size,
        page_count: 5,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        job: null,
      })
    ),
    retry: vi.fn(),
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
    const validFile = new File(["test content"], "valid.pdf", {
      type: "application/pdf",
    });
    expect(validatePdfFile(validFile).valid).toBe(true);

    const txtFile = new File(["test content"], "invalid.txt", {
      type: "text/plain",
    });
    expect(validatePdfFile(txtFile).valid).toBe(false);

    const emptyFile = new File([], "empty.pdf", {
      type: "application/pdf",
    });
    expect(validatePdfFile(emptyFile).valid).toBe(false);
  });

  it("enforces 10 MiB upload limit boundaries", () => {
    const oversized = new File(
      [new Uint8Array(10 * 1024 * 1024 + 1)],
      "oversized.pdf",
      { type: "application/pdf" }
    );
    expect(validatePdfFile(oversized).valid).toBe(false);
  });

  it("uploads PDF and refreshes authoritative documents list", async () => {
    const file = new File(["dummy pdf bytes"], "paper.pdf", {
      type: "application/pdf",
    });

    const res = await uploadDocument(10, file);

    expect(res.status).toBe("ready");
    expect(res.filename).toBe("paper.pdf");
    expect(documentApi.upload).toHaveBeenCalledTimes(1);

    const storeDocs = useDocumentStore.getState().documentsByChat[10];
    expect(storeDocs).toHaveLength(1);
    expect(storeDocs[0].filename).toBe("paper.pdf");
  });

  it("prevents concurrent upload on same chat", async () => {
    useDocumentStore.getState().setUploading(10, true);

    const file = new File(["dummy"], "second.pdf", {
      type: "application/pdf",
    });

    await expect(uploadDocument(10, file)).rejects.toThrow(
      "An upload is already in progress for this chat."
    );
  });

  it("maintains chat isolation during upload", async () => {
    const file = new File(["dummy"], "chat20.pdf", {
      type: "application/pdf",
    });

    await uploadDocument(20, file);

    const store = useDocumentStore.getState();
    expect(store.documentsByChat[20]).toHaveLength(1);
    expect(store.documentsByChat[10] || []).toHaveLength(0);
  });
});