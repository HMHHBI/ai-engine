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

  const [asyncResolvedDoc, setAsyncResolvedDoc] = useState<Document | null>(null);
  const [fetchState, setFetchState] = useState<{
    docId: number | null;
    status: DocumentResolutionStatus;
    error: string | null;
  }>({
    docId: null,
    status: "idle",
    error: null,
  });

  useEffect(() => {
    if (candidateDocId === null || activeChatId === null) {
      setAsyncResolvedDoc(null);
      setFetchState({ docId: null, status: "idle", error: null });
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
      setAsyncResolvedDoc(inMemoryDoc);
      setFetchState({ docId: candidateDocId, status: "resolved", error: null });
      return;
    }

    // 2. Fetch uncached document from API
    let isCancelled = false;
    const controller = new AbortController();

    setFetchState({ docId: candidateDocId, status: "loading", error: null });

    documentApi
      .get(candidateDocId, { signal: controller.signal })
      .then((doc) => {
        if (isCancelled) return;

        // Verify document belongs to active chat session and is ready
        if (doc.chat_id !== activeChatId) {
          setAsyncResolvedDoc(null);
          setFetchState({
            docId: candidateDocId,
            status: "not_found",
            error: "Document does not belong to active chat session.",
          });
          return;
        }

        if (doc.status !== "ready") {
          setAsyncResolvedDoc(null);
          setFetchState({
            docId: candidateDocId,
            status: "error",
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

        setAsyncResolvedDoc(doc);
        setFetchState({ docId: candidateDocId, status: "resolved", error: null });
      })
      .catch((err: unknown) => {
        if (isCancelled) return;
        const errorMsg =
          err instanceof Error ? err.message : "Failed to load document";
        const isNotFound =
          errorMsg.toLowerCase().includes("not found") ||
          (err && typeof err === "object" && "status" in err && err.status === 404);

        setAsyncResolvedDoc(null);
        setFetchState({
          docId: candidateDocId,
          status: isNotFound ? "not_found" : "error",
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

  // Fast path: cached in memory
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

  // Async path matching current candidate
  if (fetchState.docId === candidateDocId) {
    return {
      status: fetchState.status,
      document: asyncResolvedDoc,
      error: fetchState.error,
    };
  }

  return {
    status: "loading",
    document: null,
    error: null,
  };
}
