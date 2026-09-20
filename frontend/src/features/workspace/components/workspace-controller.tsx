"use client";

import { useSearchParams } from "next/navigation";
import { ChatArea } from "@/features/chat/components/chat-area";
import { ResearchWorkspace } from "./research-workspace";
import { parseCandidateDocId } from "../utils/workspace-url";
import { useResolvedWorkspaceDocument } from "../hooks/use-resolved-workspace-document";

export function WorkspaceController() {
  const searchParams = useSearchParams();
  const candidateDocId = parseCandidateDocId(searchParams);
  const { status, document: resolvedDocument } = useResolvedWorkspaceDocument(candidateDocId);

  // If there is no resolved document (idle, loading, not_found, or error),
  // retain normal standard ChatArea
  if (status !== "resolved" || !resolvedDocument) {
    return <ChatArea />;
  }

  return <ResearchWorkspace document={resolvedDocument} />;
}
