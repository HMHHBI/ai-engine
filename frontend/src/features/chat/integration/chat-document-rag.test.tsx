import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document } from "@/types/api";
import { useDocumentStore } from "@/features/documents/document-store";
import {
  selectDocument,
  deleteDocument,
} from "@/features/documents/document-actions";
import { buildStreamPayload } from "@/features/chat/actions/chat-actions";

const { mockInvalidate, mockDelete } = vi.hoisted(() => ({
  mockInvalidate: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@/features/chat/stream/chat-request-controller", () => ({
  chatRequestController: {
    invalidate: mockInvalidate,
  },
}));

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    update: vi.fn(),
    delete: mockDelete,
    listForChat: vi.fn(),
    get: vi.fn(),
  },
}));

function makeDocument(
  id: number,
  chatId = 10,
  overrides: Partial<Document> = {},
): Document {
  return {
    id,
    user_id: 1,
    chat_id: chatId,
    filename: `doc-${id}.pdf`,
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("F3-B.6: Chat/RAG Integration & End-to-End Verification", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("5. No selection sends null/omitted document_id for automatic backend fallback", () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);

    const selectedDocId =
      useDocumentStore.getState().selectedDocumentIdByChat[1] ?? null;
    expect(selectedDocId).toBeNull();

    const payload = buildStreamPayload(
      {
        chatId: 1,
        prompt: "Summarize the documents",
        model: "gemini-2.5-flash",
        provider: "gemini",
      },
      selectedDocId,
    );

    expect(payload.chat_id).toBe(1);
    expect(payload.prompt).toBe("Summarize the documents");
    expect(payload.document_id).toBeUndefined();
  });

  it("6. Explicit selection passes exact document_id into stream payload", () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);

    const selectResult = selectDocument(1, 101);
    expect(selectResult).toBe(true);

    const selectedDocId =
      useDocumentStore.getState().selectedDocumentIdByChat[1];
    expect(selectedDocId).toBe(101);

    const payload = buildStreamPayload(
      {
        chatId: 1,
        prompt: "Focus only on doc A",
        model: "gemini-2.5-flash",
        provider: "gemini",
      },
      selectedDocId,
    );

    expect(payload.chat_id).toBe(1);
    expect(payload.document_id).toBe(101);
  });

  it("9. Chat switching maintains strict document selection isolation", () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(201, 2);

    useDocumentStore.getState().setDocuments(1, [docA]);
    useDocumentStore.getState().setDocuments(2, [docB]);

    selectDocument(1, 101);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBe(101);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[2]).toBeNull();

    // Outgoing payload for Chat 2 must NOT inherit Chat 1 selection
    const chat2Selection =
      useDocumentStore.getState().selectedDocumentIdByChat[2] ?? null;
    const payloadChat2 = buildStreamPayload(
      {
        chatId: 2,
        prompt: "Chat 2 prompt",
      },
      chat2Selection,
    );

    expect(payloadChat2.chat_id).toBe(2);
    expect(payloadChat2.document_id).toBeUndefined();
  });

  it("10. Same-chat document switching updates subsequent stream payloads", () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);

    selectDocument(1, 101);
    const payload1 = buildStreamPayload({ chatId: 1, prompt: "Query 1" }, 101);
    expect(payload1.document_id).toBe(101);

    selectDocument(1, 102);
    const payload2 = buildStreamPayload({ chatId: 1, prompt: "Query 2" }, 102);
    expect(payload2.document_id).toBe(102);
  });

  it("11. Changing document selection invalidates the active stream controller", () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);

    selectDocument(1, 101);
    expect(mockInvalidate).toHaveBeenCalledTimes(1);

    selectDocument(1, 102);
    expect(mockInvalidate).toHaveBeenCalledTimes(2);

    // Toggling selection off also invalidates active stream
    selectDocument(1, 102);
    expect(mockInvalidate).toHaveBeenCalledTimes(3);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBeNull();
  });

  it("12. Deleting the selected document resets selection to null and falls back", async () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);
    selectDocument(1, 101);

    mockDelete.mockResolvedValue(undefined);
    await deleteDocument(1, 101);

    const remainingSelection =
      useDocumentStore.getState().selectedDocumentIdByChat[1];
    expect(remainingSelection).toBeNull();

    const fallbackPayload = buildStreamPayload(
      { chatId: 1, prompt: "Next question" },
      remainingSelection,
    );
    expect(fallbackPayload.document_id).toBeUndefined();
  });

  it("13. Deleting a non-selected document preserves the active document selection", async () => {
    const docA = makeDocument(101, 1);
    const docB = makeDocument(102, 1);
    useDocumentStore.getState().setDocuments(1, [docA, docB]);
    selectDocument(1, 101);

    mockDelete.mockResolvedValue(undefined);
    await deleteDocument(1, 102);

    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBe(101);
    const payload = buildStreamPayload({ chatId: 1, prompt: "Query" }, 101);
    expect(payload.document_id).toBe(101);
  });

  it("14 & 15. Processing and failed documents cannot be selected and clear existing selection", () => {
    const docProcessing = makeDocument(201, 1, { status: "processing" });
    const docFailed = makeDocument(202, 1, { status: "failed" });
    const docReady = makeDocument(203, 1, { status: "ready" });

    useDocumentStore
      .getState()
      .setDocuments(1, [docProcessing, docFailed, docReady]);

    expect(selectDocument(1, 201)).toBe(false);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBeNull();

    expect(selectDocument(1, 202)).toBe(false);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBeNull();

    expect(selectDocument(1, 203)).toBe(true);
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBe(203);

    // Transitioning active document to failed clears selection
    useDocumentStore.getState().updateDocumentInStore({
      ...docReady,
      status: "failed",
    });
    expect(useDocumentStore.getState().selectedDocumentIdByChat[1]).toBeNull();
  });
});
