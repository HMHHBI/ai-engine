import {
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";

import {
  useDocumentStore,
} from "./document-store";

import type { Document } from "@/types/api";

function documentFixture(
  overrides: Partial<Document> = {},
): Document {
  return {
    id: 1,
    user_id: 1,
    chat_id: 42,
    filename: "paper.pdf",
    mime_type: "application/pdf",
    file_size: 1000,
    page_count: 10,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-06T10:00:00Z",
    ...overrides,
  };
}

describe("document-store session hydration", () => {
  beforeEach(() => {
    useDocumentStore.getState().reset();
  });

  it("hydrates documents and selects the preferred ready document", () => {
    const documents = [
      documentFixture({
        id: 1,
        filename: "old.pdf",
        updated_at: "2026-10-01T10:00:00Z",
      }),
      documentFixture({
        id: 2,
        filename: "new.pdf",
        updated_at: "2026-10-06T10:00:00Z",
      }),
    ];

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        42,
        documents,
        2,
      );

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[42],
    ).toEqual(documents);

    expect(
      state.selectedDocumentIdByChat[42],
    ).toBe(2);
  });

  it("rejects a preferred document that is not ready", () => {
    const documents = [
      documentFixture({
        id: 1,
        status: "failed",
      }),
    ];

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        42,
        documents,
        1,
      );

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[42],
    ).toBeNull();
  });

  it("rejects a preferred document belonging to another chat", () => {
    const documents = [
      documentFixture({
        id: 1,
        chat_id: 99,
      }),
    ];

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        42,
        documents,
        1,
      );

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[42],
    ).toBeNull();
  });

  it("supports zero-document sessions", () => {
    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        42,
        [],
        null,
      );

    const state =
      useDocumentStore.getState();

    expect(
      state.documentsByChat[42],
    ).toEqual([]);

    expect(
      state.selectedDocumentIdByChat[42],
    ).toBeNull();
  });

  it("does not allow selecting a processing document", () => {
    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        42,
        [
          documentFixture({
            id: 7,
            status: "processing",
          }),
        ],
        null,
      );

    useDocumentStore
      .getState()
      .setSelectedDocument(
        42,
        7,
      );

    expect(
      useDocumentStore.getState()
        .selectedDocumentIdByChat[42],
    ).toBeNull();
  });
});