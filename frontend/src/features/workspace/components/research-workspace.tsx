"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";

import { ChatArea } from "@/features/chat/components/chat-area";
import { DocumentStatusBadge } from "@/features/documents/components/DocumentStatusBadge";
import { DocumentPane } from "./document-pane";
import { useWorkspaceUiStore } from "../store/workspace-ui-store";
import {
  WORKSPACE_DOCUMENT_MIN_WIDTH,
  WORKSPACE_DOCUMENT_MAX_RATIO,
  WORKSPACE_DOCUMENT_DEFAULT_RATIO,
  WORKSPACE_CHAT_MIN_WIDTH,
} from "../constants/layout";
import type { Document as WorkspaceDoc, RetrievedSource } from "@/types/api";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";
import { createPdfNavigationTarget } from "@/features/pdf/utils/pdf-navigation-utils";

interface ResearchWorkspaceProps {
  document: WorkspaceDoc;
  onClose?: () => void;
}

const RESPONSIVE_BREAKPOINT_PX = 1024;

export function ResearchWorkspace({
  document: activeDoc,
  onClose,
}: ResearchWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);

  const panelWidth = useWorkspaceUiStore((state) => state.panelWidth);
  const setPanelWidth = useWorkspaceUiStore((state) => state.setPanelWidth);
  const isCollapsed = useWorkspaceUiStore(
    (state) => state.isDocumentPaneCollapsed,
  );
  const setCollapsed = useWorkspaceUiStore(
    (state) => state.setDocumentPaneCollapsed,
  );

  const [isNarrow, setIsNarrow] = useState<boolean>(false);
  const [pdfNavigationTarget, setPdfNavigationTarget] =
    useState<PdfNavigationTarget | null>(null);
  const navigationRequestIdRef = useRef(0);

  useEffect(() => {
    function checkWidth() {
      if (typeof window !== "undefined") {
        setIsNarrow(window.innerWidth < RESPONSIVE_BREAKPOINT_PX);
      }
    }

    checkWidth();
    window.addEventListener("resize", checkWidth);

    return () => window.removeEventListener("resize", checkWidth);
  }, []);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const containerWidth =
      containerRef.current.getBoundingClientRect().width;

    if (containerWidth > 0 && panelWidth <= WORKSPACE_DOCUMENT_MIN_WIDTH) {
      const defaultCalculated = Math.round(
        containerWidth * WORKSPACE_DOCUMENT_DEFAULT_RATIO,
      );

      const maxAllowed = Math.round(
        containerWidth * WORKSPACE_DOCUMENT_MAX_RATIO,
      );

      const safeWidth = Math.max(
        WORKSPACE_DOCUMENT_MIN_WIDTH,
        Math.min(defaultCalculated, maxAllowed),
      );

      setPanelWidth(safeWidth);
    }
  }, [panelWidth, setPanelWidth]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();

    isDraggingRef.current = true;

    (e.target as HTMLElement).setPointerCapture(e.pointerId);

    if (typeof window !== "undefined") {
      window.document.body.style.cursor = "col-resize";
      window.document.body.style.userSelect = "none";
    }
  }, []);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDraggingRef.current || !containerRef.current) {
        return;
      }

      const containerRect =
        containerRef.current.getBoundingClientRect();

      const containerWidth = containerRect.width;
      const targetDocWidth = containerRect.right - e.clientX;

      const minDocWidth = WORKSPACE_DOCUMENT_MIN_WIDTH;
      const maxDocByRatio = Math.round(
        containerWidth * WORKSPACE_DOCUMENT_MAX_RATIO,
      );
      const maxDocByChatFloor =
        containerWidth - WORKSPACE_CHAT_MIN_WIDTH;

      const effectiveMax = Math.max(
        minDocWidth,
        Math.min(maxDocByRatio, maxDocByChatFloor),
      );

      const clampedWidth = Math.max(
        minDocWidth,
        Math.min(targetDocWidth, effectiveMax),
      );

      setPanelWidth(clampedWidth);
    },
    [setPanelWidth],
  );

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (!isDraggingRef.current) {
      return;
    }

    isDraggingRef.current = false;

    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // Pointer capture may already have been released.
    }

    if (typeof window !== "undefined") {
      window.document.body.style.cursor = "";
      window.document.body.style.userSelect = "";
    }
  }, []);

  const handleResponsiveClose = useCallback(() => {
    if (isNarrow) {
      setCollapsed(true);
    } else if (onClose) {
      onClose();
    }
  }, [isNarrow, setCollapsed, onClose]);

  const handleCitationClick = useCallback(
    (source: RetrievedSource) => {
      navigationRequestIdRef.current += 1;

      const target = createPdfNavigationTarget(
        source,
        activeDoc.id,
        navigationRequestIdRef.current,
      );

      if (!target) {
        return;
      }

      setPdfNavigationTarget(target);

      if (isNarrow && isCollapsed) {
        setCollapsed(false);
      }
    },
    [activeDoc.id, isNarrow, isCollapsed, setCollapsed],
  );

  return (
    <div
      ref={containerRef}
      data-testid="workspace-split-pane"
      className="relative flex h-full w-full overflow-hidden"
      onPointerMove={!isNarrow ? handlePointerMove : undefined}
      onPointerUp={!isNarrow ? handlePointerUp : undefined}
    >
      <div
        data-testid="workspace-chat-pane"
        className="flex h-full min-w-0 flex-1 flex-col overflow-hidden"
        style={{
          minWidth: !isNarrow
            ? `${WORKSPACE_CHAT_MIN_WIDTH}px`
            : undefined,
        }}
      >
        <div
          data-testid="research-workspace-context"
          className="shrink-0 border-b border-border bg-background px-4 py-2.5 sm:px-5"
        >
          <div className="mx-auto flex w-full max-w-3xl items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="size-4" aria-hidden="true" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Researching
              </p>

              <p
                data-testid="research-workspace-document-title"
                className="truncate text-sm font-semibold text-foreground"
                title={activeDoc.filename}
              >
                {activeDoc.filename}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {activeDoc.page_count !== null && (
                <span
                  data-testid="research-workspace-page-count"
                  className="hidden text-xs text-muted-foreground sm:inline"
                >
                  {activeDoc.page_count}{" "}
                  {activeDoc.page_count === 1 ? "page" : "pages"}
                </span>
              )}

              <DocumentStatusBadge status={activeDoc.status} />
            </div>
          </div>
        </div>

        <ChatArea
          documentId={activeDoc.id}
          onCitationClick={handleCitationClick}
        />
      </div>

      {isNarrow && isCollapsed && (
        <button
          type="button"
          data-testid="workspace-reopen-document-button"
          onClick={() => setCollapsed(false)}
          className="fixed bottom-20 right-4 z-30 flex items-center space-x-2 rounded-full bg-primary px-3 py-2 text-xs font-medium text-primary-foreground shadow-lg transition-all hover:bg-primary/90"
        >
          <FileText className="h-4 w-4" />
          <span>View Document</span>
        </button>
      )}

      {isNarrow && !isCollapsed && (
        <>
          <div
            data-testid="workspace-drawer-backdrop"
            aria-hidden="true"
            onClick={() => setCollapsed(true)}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]"
          />

          <div
            data-testid="workspace-responsive-drawer"
            role="dialog"
            aria-label={activeDoc.filename}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-background shadow-xl"
          >
            <DocumentPane
              document={activeDoc}
              onClose={handleResponsiveClose}
              navigationTarget={pdfNavigationTarget}
            />
          </div>
        </>
      )}

      {!isNarrow && !isCollapsed && (
        <>
          <div
            data-testid="workspace-resize-handle"
            role="separator"
            aria-orientation="vertical"
            tabIndex={0}
            onPointerDown={handlePointerDown}
            className="z-10 h-full w-1.5 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-primary/30 active:bg-primary/50"
          />

          <div
            data-testid="workspace-document-pane-container"
            className="h-full shrink-0 overflow-hidden"
            style={{
              width: `${panelWidth}px`,
              minWidth: `${WORKSPACE_DOCUMENT_MIN_WIDTH}px`,
            }}
          >
            <DocumentPane
              document={activeDoc}
              onClose={onClose}
              navigationTarget={pdfNavigationTarget}
            />
          </div>
        </>
      )}
    </div>
  );
}
