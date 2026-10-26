"use client";

import { useEffect, useState } from "react";
import type { Document } from "@/types/api";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useWorkspaceStore } from "@/features/workspace/store/workspace-store";
import { useDocumentStore } from "@/features/documents/document-store";
import { documentApi } from "@/lib/api/documents";
import { workspaceService } from "@/features/workspace/services/workspace-service";

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
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);

  const chatDocuments = useDocumentStore((state) =>
    activeChatId === null
      ? EMPTY_DOCS
      : state.documentsByChat[activeChatId] ?? EMPTY_DOCS,
  );

  // In-memory cache for chat context
  const cachedDoc: Document | null =
    candidateDocId !== null && activeChatId !== null
      ? (chatDocuments.find(
          (item) =>
            item.id === candidateDocId &&
            item.chat_id === activeChatId &&
            item.status === "ready",
        ) ?? null)
      : null;

  const [fetchState, setFetchState] = useState<{
    docId: number | null;
    chatId: number | null;
    workspaceId: number | null;
    status: DocumentResolutionStatus;
    document: Document | null;
    error: string | null;
  }>({
    docId: null,
    chatId: null,
    workspaceId: null,
    status: "idle",
    document: null,
    error: null,
  });

  useEffect(() => {
    if (candidateDocId === null || cachedDoc !== null) {
      return;
    }

    if (activeChatId === null && activeWorkspaceId === null) {
      return;
    }

    let isCancelled = false;
    const controller = new AbortController();

    async function resolveDocument() {
      try {
        const doc = await documentApi.get(candidateDocId!, {
          signal: controller.signal,
        });
        if (isCancelled) return;

        // Workspace mode check: If an active workspace is present, verify membership against workspace documents
        if (activeWorkspaceId !== null) {
          let wsDocs =
            useWorkspaceStore.getState().documentsByWorkspace[activeWorkspaceId];

          if (!wsDocs || wsDocs.length === 0) {
            try {
              wsDocs = await workspaceService.listDocuments(activeWorkspaceId);
              if (!isCancelled) {
                useWorkspaceStore
                  .getState()
                  .setWorkspaceDocuments(activeWorkspaceId, wsDocs);
              }
            } catch {
              wsDocs = [];
            }
          }

          if (isCancelled) return;

          const belongsToWorkspace = wsDocs.some(
            (d) => d.document_id === doc.id,
          );

          if (!belongsToWorkspace) {
            setFetchState({
              docId: candidateDocId,
              chatId: activeChatId,
              workspaceId: activeWorkspaceId,
              status: "not_found",
              document: null,
              error: "Document does not belong to the active workspace.",
            });
            return;
          }
        } else if (activeChatId !== null) {
          // Pure chat mode check: document must explicitly belong to the active chat
          if (doc.chat_id !== activeChatId) {
            setFetchState({
              docId: candidateDocId,
              chatId: activeChatId,
              workspaceId: null,
              status: "not_found",
              document: null,
              error: "Document does not belong to active chat session.",
            });
            return;
          }
        }

        if (doc.status !== "ready") {
          setFetchState({
            docId: candidateDocId,
            chatId: activeChatId,
            workspaceId: activeWorkspaceId,
            status: "error",
            document: null,
            error: `Document is not ready for viewing (status: ${doc.status}).`,
          });
          return;
        }

        if (activeChatId !== null) {
          const store = useDocumentStore.getState();
          const existingDocs = store.documentsByChat[activeChatId] ?? [];
          if (!existingDocs.some((d) => d.id === doc.id)) {
            store.setDocuments(activeChatId, [...existingDocs, doc]);
          }
        }

        setFetchState({
          docId: candidateDocId,
          chatId: activeChatId,
          workspaceId: activeWorkspaceId,
          status: "resolved",
          document: doc,
          error: null,
        });
      } catch (err: unknown) {
        if (isCancelled) return;
        const errorMsg =
          err instanceof Error ? err.message : "Failed to load document";
        const isNotFound =
          errorMsg.toLowerCase().includes("not found") ||
          (err &&
            typeof err === "object" &&
            "status" in err &&
            (err as { status?: number }).status === 404);

        setFetchState({
          docId: candidateDocId,
          chatId: activeChatId,
          workspaceId: activeWorkspaceId,
          status: isNotFound ? "not_found" : "error",
          document: null,
          error: errorMsg,
        });
      }
    }

    resolveDocument();

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [candidateDocId, activeChatId, activeWorkspaceId, cachedDoc]);

  if (candidateDocId === null) {
    return {
      status: "idle",
      document: null,
      error: null,
    };
  }

  if (cachedDoc) {
    return {
      status: "resolved",
      document: cachedDoc,
      error: null,
    };
  }

  if (
    fetchState.docId === candidateDocId &&
    fetchState.chatId === activeChatId &&
    fetchState.workspaceId === activeWorkspaceId
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
