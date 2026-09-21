"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { ChatArea } from "@/features/chat/components/chat-area";
import { DocumentPane } from "./document-pane";
import { useWorkspaceUiStore } from "../store/workspace-ui-store";
import {
  WORKSPACE_DOCUMENT_MIN_WIDTH,
  WORKSPACE_DOCUMENT_MAX_RATIO,
  WORKSPACE_DOCUMENT_DEFAULT_RATIO,
  WORKSPACE_CHAT_MIN_WIDTH,
} from "../constants/layout";
import type { Document as WorkspaceDoc } from "@/types/api";

interface ResearchWorkspaceProps {
  document: WorkspaceDoc;
  onClose?: () => void;
}

const RESPONSIVE_BREAKPOINT_PX = 1024;

export function ResearchWorkspace({ document: activeDoc, onClose }: ResearchWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);

  const panelWidth = useWorkspaceUiStore((state) => state.panelWidth);
  const setPanelWidth = useWorkspaceUiStore((state) => state.setPanelWidth);
  const isCollapsed = useWorkspaceUiStore((state) => state.isDocumentPaneCollapsed);
  const setCollapsed = useWorkspaceUiStore((state) => state.setDocumentPaneCollapsed);

  const [isNarrow, setIsNarrow] = useState<boolean>(false);

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
    if (!containerRef.current) return;
    const containerWidth = containerRef.current.getBoundingClientRect().width;
    if (containerWidth > 0 && panelWidth <= WORKSPACE_DOCUMENT_MIN_WIDTH) {
      const defaultCalculated = Math.round(containerWidth * WORKSPACE_DOCUMENT_DEFAULT_RATIO);
      const maxAllowed = Math.round(containerWidth * WORKSPACE_DOCUMENT_MAX_RATIO);
      const safeWidth = Math.max(
        WORKSPACE_DOCUMENT_MIN_WIDTH,
        Math.min(defaultCalculated, maxAllowed)
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
      if (!isDraggingRef.current || !containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;

      const targetDocWidth = containerRect.right - e.clientX;

      const minDocWidth = WORKSPACE_DOCUMENT_MIN_WIDTH;
      const maxDocByRatio = Math.round(containerWidth * WORKSPACE_DOCUMENT_MAX_RATIO);
      const maxDocByChatFloor = containerWidth - WORKSPACE_CHAT_MIN_WIDTH;

      const effectiveMax = Math.max(minDocWidth, Math.min(maxDocByRatio, maxDocByChatFloor));
      const clampedWidth = Math.max(minDocWidth, Math.min(targetDocWidth, effectiveMax));

      setPanelWidth(clampedWidth);
    },
    [setPanelWidth]
  );

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // safe fallback
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

  return (
    <div
      ref={containerRef}
      data-testid="workspace-split-pane"
      className="flex h-full w-full overflow-hidden relative"
      onPointerMove={!isNarrow ? handlePointerMove : undefined}
      onPointerUp={!isNarrow ? handlePointerUp : undefined}
    >
      {/* Primary Chat Surface */}
      <div
        data-testid="workspace-chat-pane"
        className="flex h-full flex-1 flex-col overflow-hidden min-w-0"
        style={{ minWidth: !isNarrow ? `${WORKSPACE_CHAT_MIN_WIDTH}px` : undefined }}
      >
        <ChatArea documentId={activeDoc.id} />
      </div>

      {/* Narrow view: Reopen button when drawer is collapsed */}
      {isNarrow && isCollapsed && (
        <button
          type="button"
          data-testid="workspace-reopen-document-button"
          onClick={() => setCollapsed(false)}
          className="fixed bottom-20 right-4 z-30 flex items-center space-x-2 rounded-full bg-primary px-3 py-2 text-xs font-medium text-primary-foreground shadow-lg hover:bg-primary/90 transition-all"
        >
          <FileText className="h-4 w-4" />
          <span>View Document</span>
        </button>
      )}

      {/* Narrow view: Responsive Sheet/Drawer with backdrop */}
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
            className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-background shadow-xl border-l border-border flex flex-col"
          >
            <DocumentPane
              document={activeDoc}
              onClose={handleResponsiveClose}
            />
          </div>
        </>
      )}

      {/* Desktop view: Split layout with resize handle */}
      {!isNarrow && !isCollapsed && (
        <>
          <div
            data-testid="workspace-resize-handle"
            role="separator"
            aria-orientation="vertical"
            tabIndex={0}
            onPointerDown={handlePointerDown}
            className="w-1.5 h-full cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors z-10 shrink-0 bg-transparent"
          />
          <div
            data-testid="workspace-document-pane-container"
            className="h-full shrink-0 overflow-hidden"
            style={{ width: `${panelWidth}px`, minWidth: `${WORKSPACE_DOCUMENT_MIN_WIDTH}px` }}
          >
            <DocumentPane document={activeDoc} onClose={onClose} />
          </div>
        </>
      )}
    </div>
  );
}
