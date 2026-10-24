"use client";

import { useEffect, useState } from "react";
import type { Document } from "@/types/api";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";
import { documentApi } from "@/lib/api/documents";

export type DocumentResolutionStatus =
  | "idle"
  | "loading"
  | "resolved"
  | "not_found"
  | "error";

export interface DocumentResolutionState {
  status: DocumentResolutionStatus;
  document: Document | null;
  error: string | null;
}

const EMPTY_DOCS: Document[] = [];

export function useResolvedWorkspaceDocument(
  candidateDocId: number | null,
): DocumentResolutionState {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const documents = useDocumentStore((state) =>
    activeChatId === null
      ? EMPTY_DOCS
      : state.documentsByChat[activeChatId] ?? EMPTY_DOCS,
  );

  const [fetchState, setFetchState] = useState<{
    docId: number | null;
    chatId: number | null;
    status: DocumentResolutionStatus;
    document: Document | null;
    error: string | null;
  }>({
    docId: null,
    chatId: null,
    status: "idle",
    document: null,
    error: null,
  });

  useEffect(() => {
    if (candidateDocId === null || activeChatId === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFetchState({
        docId: null,
        chatId: null,
        status: "idle",
        document: null,
        error: null,
      });
      return;
    }

    // 1. Check in-memory store first
    const inMemoryDoc = documents.find(
      (item) =>
        item.id === candidateDocId &&
        item.chat_id === activeChatId &&
        item.status === "ready",
    );

    if (inMemoryDoc) {
      setFetchState({
        docId: candidateDocId,
        chatId: activeChatId,
        status: "resolved",
        document: inMemoryDoc,
        error: null,
      });
      return;
    }

    // 2. Fetch uncached document from API
    let isCancelled = false;
    const controller = new AbortController();
    setFetchState({
      docId: candidateDocId,
      chatId: activeChatId,
      status: "loading",
      document: null,
      error: null,
    });

    documentApi
      .get(candidateDocId, { signal: controller.signal })
      .then((doc) => {
        if (isCancelled) return;

        // Verify document belongs to active chat session and is ready
        if (doc.chat_id !== activeChatId) {
          setFetchState({
            docId: candidateDocId,
            chatId: activeChatId,
            status: "not_found",
            document: null,
            error: "Document does not belong to active chat session.",
          });
          return;
        }

        if (doc.status !== "ready") {
          setFetchState({
            docId: candidateDocId,
            chatId: activeChatId,
            status: "error",
            document: null,
            error: `Document is not ready for viewing (status: ${doc.status}).`,
          });
          return;
        }

        // Cache document into document store via setDocuments
        const store = useDocumentStore.getState();
        const existingDocs = store.documentsByChat[activeChatId] ?? [];
        if (!existingDocs.some((d) => d.id === doc.id)) {
          store.setDocuments(activeChatId, [...existingDocs, doc]);
        }

        setFetchState({
          docId: candidateDocId,
          chatId: activeChatId,
          status: "resolved",
          document: doc,
          error: null,
        });
      })
      .catch((err: unknown) => {
        if (isCancelled) return;
        const errorMsg =
          err instanceof Error ? err.message : "Failed to load document";
        const isNotFound =
          errorMsg.toLowerCase().includes("not found") ||
          (err && typeof err === "object" && "status" in err && err.status === 404);

        setFetchState({
          docId: candidateDocId,
          chatId: activeChatId,
          status: isNotFound ? "not_found" : "error",
          document: null,
          error: errorMsg,
        });
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [candidateDocId, activeChatId, documents]);

  if (activeChatId === null || candidateDocId === null) {
    return {
      status: "idle",
      document: null,
      error: null,
    };
  }

  // Fast path: cached in memory for current active chat
  const cached = documents.find(
    (item) =>
      item.id === candidateDocId &&
      item.chat_id === activeChatId &&
      item.status === "ready",
  );

  if (cached) {
    return {
      status: "resolved",
      document: cached,
      error: null,
    };
  }

  // Chat-scoped match check: ensures no stale doc from another chat is ever leaked
  if (
    fetchState.docId === candidateDocId &&
    fetchState.chatId === activeChatId
  ) {
    return {
      status: fetchState.status,
      document: fetchState.document,
      error: fetchState.error,
    };
  }

  return {
    status: "loading",
    document: null,
    error: null,
  };
}
