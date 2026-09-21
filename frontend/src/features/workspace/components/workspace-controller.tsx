"use client";

import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useCallback } from "react";
import { ChatArea } from "@/features/chat/components/chat-area";
import { ResearchWorkspace } from "./research-workspace";
import { parseCandidateDocId } from "../utils/workspace-url";
import { useResolvedWorkspaceDocument } from "../hooks/use-resolved-workspace-document";
import { selectDocument } from "@/features/documents/document-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";

export function WorkspaceController() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const candidateDocId = parseCandidateDocId(searchParams);
  const { status, document: resolvedDocument } = useResolvedWorkspaceDocument(candidateDocId);

  const handleCloseDocument = useCallback(() => {
    // Clear legacy store selection for current chat to ensure no hidden fallback persists
    const currentChatId = useChatSessionStore.getState().activeChatId;
    if (currentChatId) {
      selectDocument(currentChatId, null);
    }

    if (typeof window !== "undefined") {
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      params.delete("docId");
      const query = params.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    }
  }, [router, pathname, searchParams]);

  // If there is no resolved document (idle, loading, not_found, or error),
  // retain normal standard ChatArea
  if (status !== "resolved" || !resolvedDocument) {
    return <ChatArea />;
  }

  return (
    <ResearchWorkspace
      document={resolvedDocument}
      onClose={handleCloseDocument}
    />
  );
}
