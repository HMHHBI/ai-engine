import {
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";

import { renderHook } from "@testing-library/react";

import { useResolvedWorkspaceDocument } from "./use-resolved-workspace-document";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";

import type { Document } from "@/types/api";

function documentFixture(
  overrides: Partial<Document> = {},
): Document {
  return {
    id: 101,
    user_id: 1,
    chat_id: 1,
    filename: "sample.pdf",
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-06T00:00:00Z",
    ...overrides,
  };
}

describe("useResolvedWorkspaceDocument", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
    useDocumentStore.getState().reset();
  });

  it("returns idle when there is no active session", () => {
    useChatStore.getState().setActiveChat(null);

    const { result } =
      renderHook(() =>
        useResolvedWorkspaceDocument(101),
      );

    expect(result.current.status).toBe("idle");
    expect(result.current.document).toBeNull();
  });

  it("resolves only documents belonging to the active session", () => {
    useChatStore.getState().setActiveChat(1);

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        1,
        [
          documentFixture({
            id: 101,
            chat_id: 1,
          }),
        ],
        101,
      );

    const { result } =
      renderHook(() =>
        useResolvedWorkspaceDocument(101),
      );

    expect(result.current.status).toBe(
      "resolved",
    );

    expect(
      result.current.document?.id,
    ).toBe(101);
  });

  it("rejects a document from another session", () => {
    useChatStore.getState().setActiveChat(2);

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        2,
        [
          documentFixture({
            id: 202,
            chat_id: 2,
          }),
        ],
        202,
      );

    const { result } =
      renderHook(() =>
        useResolvedWorkspaceDocument(101),
      );

    expect(result.current.status).toBe(
      "not_found",
    );

    expect(result.current.document).toBeNull();
  });

  it("does not expose a failed document", () => {
    useChatStore.getState().setActiveChat(1);

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        1,
        [
          documentFixture({
            id: 101,
            status: "failed",
          }),
        ],
        null,
      );

    const { result } =
      renderHook(() =>
        useResolvedWorkspaceDocument(101),
      );

    expect(result.current.status).toBe(
      "not_found",
    );

    expect(result.current.document).toBeNull();
  });

  it("does not expose the previous session document after switching sessions", () => {
    useChatStore.getState().setActiveChat(1);

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        1,
        [
          documentFixture({
            id: 101,
            chat_id: 1,
          }),
        ],
        101,
      );

    const { result, rerender } =
      renderHook(
        ({ docId }) =>
          useResolvedWorkspaceDocument(
            docId,
          ),
        {
          initialProps: {
            docId: 101 as number | null,
          },
        },
      );

    expect(result.current.document?.id).toBe(
      101,
    );

    useChatStore
      .getState()
      .setActiveChat(2);

    useDocumentStore
      .getState()
      .hydrateChatDocuments(
        2,
        [
          documentFixture({
            id: 202,
            chat_id: 2,
          }),
        ],
        202,
      );

    rerender({
      docId: 101,
    });

    expect(
      result.current.document,
    ).toBeNull();

    expect(result.current.status).toBe(
      "not_found",
    );
  });
});