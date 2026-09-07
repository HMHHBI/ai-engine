import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Document } from "@/types/api";
import {
  clearDocumentSelection,
  selectDocument,
} from "./document-actions";
import { useDocumentStore } from "./document-store";

const { invalidateMock } = vi.hoisted(() => ({
  invalidateMock: vi.fn(),
}));

vi.mock("@/features/chat/stream/chat-request-controller", () => ({
  chatRequestController: {
    invalidate: invalidateMock,
  },
}));

function makeDocument(
  overrides: Partial<Document> = {},
): Document {
  return {
    id: 1,
    user_id: 1,
    chat_id: 10,
    filename: "document.pdf",
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 2,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("document selection", () => {
  beforeEach(() => {
    invalidateMock.mockReset();
    useDocumentStore.getState().reset();
  });

  it("selects a ready document", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    const result = selectDocument(10, 101);

    expect(result).toBe(true);
    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBe(101);
    expect(invalidateMock).toHaveBeenCalledTimes(1);
  });

  it("replaces an existing selection", () => {
    const first = makeDocument({
      id: 101,
      chat_id: 10,
    });

    const second = makeDocument({
      id: 102,
      chat_id: 10,
      filename: "second.pdf",
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [first, second]);

    selectDocument(10, 101);
    selectDocument(10, 102);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBe(102);
    expect(invalidateMock).toHaveBeenCalledTimes(2);
  });

  it("toggles the selected document off", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    selectDocument(10, 101);
    selectDocument(10, 101);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
    expect(invalidateMock).toHaveBeenCalledTimes(2);
  });

  it("rejects processing documents", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
      status: "processing",
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    const result = selectDocument(10, 101);

    expect(result).toBe(false);
    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
    expect(invalidateMock).not.toHaveBeenCalled();
  });

  it("rejects failed documents", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
      status: "failed",
      error_message: "Embedding failed",
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    const result = selectDocument(10, 101);

    expect(result).toBe(false);
    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
  });

  it("rejects an unknown document", () => {
    useDocumentStore
      .getState()
      .setDocuments(10, []);

    const result = selectDocument(10, 999);

    expect(result).toBe(false);
    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
  });

  it("keeps selection isolated between chats", () => {
    const chatADocument = makeDocument({
      id: 101,
      chat_id: 10,
    });

    const chatBDocument = makeDocument({
      id: 201,
      chat_id: 20,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [chatADocument]);

    useDocumentStore
      .getState()
      .setDocuments(20, [chatBDocument]);

    selectDocument(10, 101);
    selectDocument(20, 201);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBe(101);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[20],
    ).toBe(201);
  });

  it("clears selection when the selected document becomes processing", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    selectDocument(10, 101);

    useDocumentStore
      .getState()
      .setDocuments(10, [
        {
          ...document,
          status: "processing",
        },
      ]);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
  });

  it("clears selection when the selected document becomes failed", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    selectDocument(10, 101);

    useDocumentStore
      .getState()
      .setDocuments(10, [
        {
          ...document,
          status: "failed",
          error_message: "Failed",
        },
      ]);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();
  });

  it("clearDocumentSelection invalidates an active stream", () => {
    const document = makeDocument({
      id: 101,
      chat_id: 10,
    });

    useDocumentStore
      .getState()
      .setDocuments(10, [document]);

    selectDocument(10, 101);

    invalidateMock.mockClear();

    clearDocumentSelection(10);

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[10],
    ).toBeNull();

    expect(invalidateMock).toHaveBeenCalledTimes(1);
  });
});