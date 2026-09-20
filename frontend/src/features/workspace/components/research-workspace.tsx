"use client";

import { useCallback, useEffect, useRef } from "react";
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

export function ResearchWorkspace({ document: activeDoc, onClose }: ResearchWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);

  const panelWidth = useWorkspaceUiStore((state) => state.panelWidth);
  const setPanelWidth = useWorkspaceUiStore((state) => state.setPanelWidth);
  const isCollapsed = useWorkspaceUiStore((state) => state.isDocumentPaneCollapsed);

  // Initialize bounded width on mount if default is too small or unset
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

      // Available space right of the cursor becomes document pane width
      const targetDocWidth = containerRect.right - e.clientX;

      // Calculate dynamic bounds against container width
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

  return (
    <div
      ref={containerRef}
      data-testid="workspace-split-pane"
      className="flex h-full w-full overflow-hidden relative"
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      {/* Left Chat Pane */}
      <div
        data-testid="workspace-chat-pane"
        className="flex h-full flex-1 flex-col overflow-hidden min-w-[420px]"
        style={{ minWidth: `${WORKSPACE_CHAT_MIN_WIDTH}px` }}
      >
        <ChatArea />
      </div>

      {/* Resize Handle */}
      {!isCollapsed && (
        <div
          data-testid="workspace-resize-handle"
          role="separator"
          aria-orientation="vertical"
          tabIndex={0}
          onPointerDown={handlePointerDown}
          className="w-1.5 h-full cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors z-10 shrink-0 bg-transparent"
        />
      )}

      {/* Right Document Pane */}
      {!isCollapsed && (
        <div
          data-testid="workspace-document-pane-container"
          className="h-full shrink-0 overflow-hidden"
          style={{ width: `${panelWidth}px`, minWidth: `${WORKSPACE_DOCUMENT_MIN_WIDTH}px` }}
        >
          <DocumentPane document={activeDoc} onClose={onClose} />
        </div>
      )}
    </div>
  );
}
