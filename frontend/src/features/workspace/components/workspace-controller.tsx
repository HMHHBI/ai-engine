"use client";

import {
  useSearchParams,
  useRouter,
  usePathname,
} from "next/navigation";
import { useCallback, useState } from "react";

import { ChatArea } from "@/features/chat/components/chat-area";
import { ResearchWorkspace } from "./research-workspace";
import { parseCandidateDocId } from "../utils/workspace-url";
import { useResolvedWorkspaceDocument } from "../hooks/use-resolved-workspace-document";
import { selectDocument } from "@/features/documents/document-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

export function WorkspaceController() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const candidateDocId = parseCandidateDocId(searchParams);

  const {
    status,
    document: resolvedDocument,
  } = useResolvedWorkspaceDocument(candidateDocId);

  const [pendingNavigationTarget, setPendingNavigationTarget] =
    useState<PdfNavigationTarget | null>(null);

  const handleCloseDocument = useCallback(() => {
    const currentChatId = useChatStore.getState().activeChatId;

    if (currentChatId) {
      selectDocument(currentChatId, null);
    }

    setPendingNavigationTarget(null);

    if (typeof window !== "undefined") {
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      params.delete("docId");

      const query = params.toString();

      router.push(query ? `${pathname}?${query}` : pathname);
    }
  }, [router, pathname, searchParams]);

  const handleDocumentNavigation = useCallback(
    (target: PdfNavigationTarget) => {
      setPendingNavigationTarget(target);

      const params = new URLSearchParams(
        searchParams?.toString() ?? "",
      );

      params.set("docId", String(target.documentId));

      const query = params.toString();

      router.push(query ? `${pathname}?${query}` : pathname);
    },
    [router, pathname, searchParams],
  );

  if (status !== "resolved" || !resolvedDocument) {
    return <ChatArea />;
  }

  return (
    <ResearchWorkspace
      document={resolvedDocument}
      onClose={handleCloseDocument}
      navigationTarget={pendingNavigationTarget}
      onDocumentNavigation={handleDocumentNavigation}
    />
  );
}
