"use client";

import { useEffect, useState } from "react";
import type { Document } from "@/types/api";
import { documentApi } from "@/lib/api/documents";

export type DocumentResolutionStatus = "idle" | "loading" | "resolved" | "not_found" | "error";

export interface DocumentResolutionState {
  status: DocumentResolutionStatus;
  document: Document | null;
  error: string | null;
}

export function useResolvedWorkspaceDocument(
  candidateDocId: number | null
): DocumentResolutionState {
  const [internalState, setInternalState] = useState<{
    resolvedCandidateId: number | null;
    status: DocumentResolutionStatus;
    document: Document | null;
    error: string | null;
  }>({
    resolvedCandidateId: candidateDocId,
    status: candidateDocId ? "loading" : "idle",
    document: null,
    error: null,
  });

  useEffect(() => {
    let isMounted = true;

    if (!candidateDocId) {
      return;
    }

    documentApi
      .get(candidateDocId)
      .then((doc) => {
        if (!isMounted) return;
        if (doc && doc.id === candidateDocId) {
          setInternalState({
            resolvedCandidateId: candidateDocId,
            status: "resolved",
            document: doc,
            error: null,
          });
        } else {
          setInternalState({
            resolvedCandidateId: candidateDocId,
            status: "not_found",
            document: null,
            error: "Document not found or inaccessible.",
          });
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        const statusCode =
          (err as { status?: number; response?: { status?: number } })?.status ??
          (err as { response?: { status?: number } })?.response?.status;

        if (statusCode === 404 || statusCode === 403) {
          setInternalState({
            resolvedCandidateId: candidateDocId,
            status: "not_found",
            document: null,
            error: "Document not found or access denied.",
          });
        } else {
          setInternalState({
            resolvedCandidateId: candidateDocId,
            status: "error",
            document: null,
            error: err instanceof Error ? err.message : "Failed to load document.",
          });
        }
      });

    return () => {
      isMounted = false;
    };
  }, [candidateDocId]);

  if (!candidateDocId) {
    return {
      status: "idle",
      document: null,
      error: null,
    };
  }

  // Prevent stale document from previous candidate leaking into current render
  if (internalState.resolvedCandidateId !== candidateDocId) {
    return {
      status: "loading",
      document: null,
      error: null,
    };
  }

  return {
    status: internalState.status,
    document: internalState.document,
    error: internalState.error,
  };
}
