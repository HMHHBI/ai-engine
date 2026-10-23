"use client";

import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { createPdfNavigationTarget } from "@/features/pdf/utils/pdf-navigation-utils";
import type { RetrievedSource } from "@/types/api";
import { Sparkles, ArrowLeft } from "lucide-react";

import { ChatArea } from "@/features/chat/components/chat-area";
import { ResearchWorkspace } from "./research-workspace";
import { WorkspaceResearchSynthesisPanel } from "./workspace-research-synthesis-panel";
import { WorkspaceDocumentManager } from "./workspace-document-manager";
import { useWorkspaceStore } from "../store/workspace-store";
import { parseCandidateDocId } from "../utils/workspace-url";
import { useResolvedWorkspaceDocument } from "../hooks/use-resolved-workspace-document";
import { selectDocument } from "@/features/documents/document-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

export function WorkspaceController() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const isResearchView = searchParams?.get("view") === "research";
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);

  const candidateDocId = parseCandidateDocId(searchParams);

  const { status, document: resolvedDocument } =
    useResolvedWorkspaceDocument(candidateDocId);

  const [pendingNavigationTarget, setPendingNavigationTarget] =
    useState<PdfNavigationTarget | null>(null);
  const navigationRequestIdRef = useRef<number>(0);

  const handleCloseDocument = useCallback(() => {
    const currentChatId = useChatStore.getState().activeChatId;

    if (currentChatId !== null) {
      selectDocument(currentChatId, null);
    }

    setPendingNavigationTarget(null);

    const params = new URLSearchParams(searchParams?.toString() ?? "");
    params.delete("docId");

    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }, [router, pathname, searchParams]);

  const handleDocumentNavigation = useCallback(
    (target: PdfNavigationTarget) => {
      setPendingNavigationTarget(target);

      const params = new URLSearchParams(searchParams?.toString() ?? "");
      params.set("docId", String(target.documentId));

      const query = params.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    },
    [router, pathname, searchParams],
  );

  const handleCitationClick = useCallback(
    (source: RetrievedSource) => {
      navigationRequestIdRef.current += 1;
      const target = createPdfNavigationTarget(
        source,
        navigationRequestIdRef.current,
      );
      if (!target) {
        return;
      }
      handleDocumentNavigation(target);
    },
    [handleDocumentNavigation],
  );

  const handleExitResearchView = useCallback(() => {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    params.delete("view");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }, [router, pathname, searchParams]);

  // View 1: Cross-Document Research Synthesis View
  if (isResearchView) {
    if (!activeWorkspaceId) {
      return (
        <div className="flex h-full flex-1 flex-col items-center justify-center gap-3 p-6 text-center" data-testid="workspace-synthesis-empty">
          <Sparkles className="size-8 text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">No Workspace Selected</h3>
          <p className="max-w-md text-xs text-muted-foreground">
            Please select or create a workspace using the switcher in the sidebar to perform cross-document research synthesis.
          </p>
          <button
            type="button"
            onClick={handleExitResearchView}
            className="flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            <ArrowLeft className="size-3.5" />
            <span>Return to chat</span>
          </button>
        </div>
      );
    }

    return (
      <div className="flex h-full flex-col overflow-hidden bg-background" data-testid="workspace-synthesis-view">
        <div className="flex items-center justify-between border-b border-border/70 px-4 py-2 bg-muted/20">
          <button
            type="button"
            onClick={handleExitResearchView}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="size-3.5" />
            <span>Back to Chat</span>
          </button>
          <span className="text-xs font-medium text-muted-foreground">Workspace Research Workbench</span>
        </div>
        <div className="flex flex-1 flex-col lg:flex-row overflow-y-auto divide-y lg:divide-y-0 lg:divide-x divide-border/60">
          <div className="flex-1 overflow-y-auto">
            <WorkspaceResearchSynthesisPanel workspaceId={activeWorkspaceId} />
          </div>
          <div className="w-full lg:w-80 shrink-0 bg-card/20 overflow-y-auto">
            <WorkspaceDocumentManager workspaceId={activeWorkspaceId} />
          </div>
        </div>
      </div>
    );
  }

  // View 2: Single Document PDF Viewer & Workspace
  if (status === "resolved" && resolvedDocument) {
    return (
      <ResearchWorkspace
        document={resolvedDocument}
        onClose={handleCloseDocument}
        navigationTarget={pendingNavigationTarget}
        onDocumentNavigation={handleDocumentNavigation}
      />
    );
  }

  // View 3: Default Chat Workspace
  return <ChatArea onCitationClick={handleCitationClick} />;
}
