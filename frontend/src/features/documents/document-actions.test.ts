import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
} from "vitest";

import {
  loadDocuments,
  updateDocument,
  deleteDocument,
  selectDocument,
  clearDocumentSelection,
  retryDocument,
} from "./document-actions";

import { documentApi } from "@/lib/api/documents";
import { useDocumentStore } from "./document-store";

import type {
  Document,
  DocumentLifecycleResponse,
} from "@/types/api";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    listForChat: vi.fn(),
    get: vi.fn(),
    upload: vi.fn(),
    retry: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

const sampleDoc: Document = {
  id: 100,
  user_id: 1,
  chat_id: 5,
  filename: "sample.pdf",
  mime_type: "application/pdf",
  file_size: 1000,
  page_count: 5,
  storage_url: null,
  status: "ready",
  error_message: null,
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
};

const failedDoc: Document = {
  ...sampleDoc,
  status: "failed",
  error_message: "Embedding failed.",
};

const lifecycleResponse: DocumentLifecycleResponse = {
  ...failedDoc,
  job: {
    id: 501,
    document_id: 100,
    status: "ready",
    attempt: 1,
    max_attempts: 3,
    error_message: null,
    queued_at: "2026-09-06T00:00:00Z",
    started_at: "2026-09-06T00:00:01Z",
    finished_at: "2026-09-06T00:00:02Z",
  },
};

describe("document-actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("loadDocuments populates store on success", async () => {
    vi.mocked(
      documentApi.listForChat,
    ).mockResolvedValueOnce([
      sampleDoc,
    ]);

    const docs =
      await loadDocuments(5);

    expect(docs).toHaveLength(1);

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[5],
    ).toHaveLength(1);

    expect(
      state.loadingByChat[5],
    ).toBe(false);

    expect(
      state.errorByChat[5],
    ).toBeNull();
  });

  it("loadDocuments captures error on failure", async () => {
    vi.mocked(
      documentApi.listForChat,
    ).mockRejectedValueOnce(
      new Error("Network Error"),
    );

    await expect(
      loadDocuments(5),
    ).rejects.toThrow(
      "Network Error",
    );

    const state =
      useDocumentStore.getState();

    expect(
      state.loadingByChat[5],
    ).toBe(false);

    expect(
      state.errorByChat[5],
    ).toBe("Network Error");
  });

  it("updateDocument updates store on success", async () => {
    useDocumentStore
      .getState()
      .setDocuments(5, [
        sampleDoc,
      ]);

    const updatedDoc = {
      ...sampleDoc,
      filename: "renamed.pdf",
    };

    vi.mocked(
      documentApi.update,
    ).mockResolvedValueOnce(
      updatedDoc,
    );

    const result =
      await updateDocument(
        100,
        {
          filename:
            "renamed.pdf",
        },
      );

    expect(
      result.filename,
    ).toBe("renamed.pdf");

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[5][0]
        .filename,
    ).toBe("renamed.pdf");

    expect(
      state.mutatingDocumentIds[100],
    ).toBe(false);
  });

  it("deleteDocument removes document from store on success", async () => {
    useDocumentStore
      .getState()
      .setDocuments(5, [
        sampleDoc,
      ]);

    vi.mocked(
      documentApi.delete,
    ).mockResolvedValueOnce(
      undefined,
    );

    await deleteDocument(
      5,
      100,
    );

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[5],
    ).toHaveLength(0);

    expect(
      state.mutatingDocumentIds[100],
    ).toBe(false);
  });

  it("deleteDocument preserves document on API error", async () => {
    useDocumentStore
      .getState()
      .setDocuments(5, [
        sampleDoc,
      ]);

    vi.mocked(
      documentApi.delete,
    ).mockRejectedValueOnce(
      new Error("Delete failed"),
    );

    await expect(
      deleteDocument(5, 100),
    ).rejects.toThrow(
      "Delete failed",
    );

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[5],
    ).toHaveLength(1);

    expect(
      state.mutatingDocumentIds[100],
    ).toBe(false);
  });

  it("retryDocument changes failed document back to ready", async () => {
    useDocumentStore
      .getState()
      .setDocuments(5, [
        failedDoc,
      ]);

    const response: DocumentLifecycleResponse =
      {
        ...lifecycleResponse,
        status: "ready",
        error_message: null,
      };

    vi.mocked(
      documentApi.retry,
    ).mockResolvedValueOnce(
      response,
    );

    const result =
      await retryDocument(
        5,
        100,
      );

    expect(
      result.status,
    ).toBe("ready");

    expect(
      useDocumentStore
        .getState()
        .documentsByChat[5][0]
        .status,
    ).toBe("ready");

    expect(
      useDocumentStore
        .getState()
        .mutatingDocumentIds[100],
    ).toBe(false);
  });

  it("selection only accepts ready documents", () => {
    useDocumentStore
      .getState()
      .setDocuments(5, [
        sampleDoc,
        {
          ...sampleDoc,
          id: 101,
          status: "indexing",
        },
        {
          ...sampleDoc,
          id: 102,
          status: "failed",
        },
      ]);

    expect(
      selectDocument(5, 100),
    ).toBe(true);

    expect(
      useDocumentStore
        .getState()
        .selectedDocumentIdByChat[5],
    ).toBe(100);

    expect(
      selectDocument(5, 101),
    ).toBe(false);

    expect(
      selectDocument(5, 102),
    ).toBe(false);

    clearDocumentSelection(5);

    expect(
      useDocumentStore
        .getState()
        .selectedDocumentIdByChat[5],
    ).toBeNull();
  });
});
