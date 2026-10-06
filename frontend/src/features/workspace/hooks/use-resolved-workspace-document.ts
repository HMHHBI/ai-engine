"use client";

import { useEffect, useState } from "react";
import type { Document } from "@/types/api";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";

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
  candidateDocId: number | null
): DocumentResolutionState {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const documents = useDocumentStore((state) =>
    activeChatId === null
      ? EMPTY_DOCS
      : state.documentsByChat[activeChatId] ?? EMPTY_DOCS
  );

  const [resolvedCandidateId, setResolvedCandidateId] =
    useState<number | null>(candidateDocId);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setResolvedCandidateId(candidateDocId);
  }, [candidateDocId, activeChatId]);

  if (activeChatId === null || candidateDocId === null) {
    return {
      status: "idle",
      document: null,
      error: null,
    };
  }

  if (resolvedCandidateId !== candidateDocId) {
    return {
      status: "loading",
      document: null,
      error: null,
    };
  }

  const document = documents.find(
    (item) =>
      item.id === candidateDocId &&
      item.chat_id === activeChatId &&
      item.status === "ready"
  );

  if (!document) {
    return {
      status: "not_found",
      document: null,
      error: "Document not found in the active research session.",
    };
  }

  return {
    status: "resolved",
    document,
    error: null,
  };
}
