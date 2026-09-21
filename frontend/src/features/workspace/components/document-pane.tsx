"use client";

import dynamic from "next/dynamic";
import { FileText, X } from "lucide-react";
import { PdfLoadingState } from "@/features/pdf/components/pdf-loading-state";
import type { Document } from "@/types/api";

const PdfViewer = dynamic(
  () =>
    import("@/features/pdf/components/pdf-viewer").then((mod) => mod.PdfViewer),
  {
    ssr: false,
    loading: () => <PdfLoadingState />,
  },
);

interface DocumentPaneProps {
  document: Document;
  onClose?: () => void;
}

export function DocumentPane({
  document,
  onClose,
}: DocumentPaneProps) {
  return (
    <div
      data-testid="workspace-document-pane"
      className="flex h-full flex-col overflow-hidden bg-background border-l border-border select-none"
    >
      {/* Document Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5 h-12 shrink-0 bg-muted/30">
        <div className="flex items-center space-x-2 truncate">
          <FileText className="h-4 w-4 text-primary shrink-0" />

          <span
            data-testid="workspace-document-title"
            className="text-sm font-medium truncate text-foreground"
            title={document.filename}
          >
            {document.filename}
          </span>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            data-testid="workspace-close-button"
            aria-label="Close document pane"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Document Metadata Strip */}
      <div className="flex items-center space-x-4 border-b border-border/50 px-4 py-1.5 text-xs text-muted-foreground bg-muted/10 shrink-0">
        <span>Status: {document.status}</span>

        {document.page_count !== null && (
          <span>{document.page_count} pages</span>
        )}

        {document.file_size !== null && (
          <span>
            {(document.file_size / 1024).toFixed(1)} KB
          </span>
        )}
      </div>

      {/* M5 PDF Viewer Boundary */}
      <div
        data-testid="pdf-viewer-boundary"
        className="min-h-0 flex-1 overflow-hidden bg-muted/5"
      >
        <PdfViewer documentId={document.id} />
      </div>
    </div>
  );
}
