"use client";

import {
  ChevronLeft,
  ChevronRight,
  FileText,
  LoaderCircle,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document as PdfDocument, Page, pdfjs } from "react-pdf";

import { useWorkspaceStore } from "@/features/workspace/store/workspace-store";
import type { Document } from "@/types/api";
import { cn } from "@/lib/utils";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface PdfViewerProps {
  document: Document | null;
  className?: string;
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2;
const ZOOM_STEP = 0.1;

export function PdfViewer({ document, className }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const viewerPage = useWorkspaceStore((state) => state.viewerPage);
  const viewerZoom = useWorkspaceStore((state) => state.viewerZoom);
  const setViewerPage = useWorkspaceStore((state) => state.setViewerPage);
  const setViewerZoom = useWorkspaceStore((state) => state.setViewerZoom);
  const resetViewer = useWorkspaceStore((state) => state.resetViewer);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pageNumber = useMemo(() => {
    if (!numPages) {
      return Math.max(1, viewerPage);
    }
    return Math.min(Math.max(1, viewerPage), numPages);
  }, [numPages, viewerPage]);

  const pageWidth = useMemo(() => {
    if (containerWidth <= 0) {
      return undefined;
    }
    return Math.max(280, containerWidth - 32);
  }, [containerWidth]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const element = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setContainerWidth(width);
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, []);

  const lastDocumentIdRef = useRef<number | null>(document?.id ?? null);

  useEffect(() => {
    if (document?.id !== lastDocumentIdRef.current) {
      lastDocumentIdRef.current = document?.id ?? null;
      setNumPages(null);
      setError(null);
      setLoading(false);
      resetViewer();
    }
  }, [document?.id, resetViewer]);

  useEffect(() => {
    if (numPages !== null && viewerPage > numPages) {
      setViewerPage(numPages);
    }
  }, [numPages, setViewerPage, viewerPage]);

  const handleLoadSuccess = useCallback(
    ({ numPages: totalPages }: { numPages: number }) => {
      setNumPages(totalPages);
      setLoading(false);
      setError(null);

      if (viewerPage > totalPages) {
        setViewerPage(totalPages);
      }
    },
    [setViewerPage, viewerPage],
  );

  const handleLoadError = useCallback((loadError: Error) => {
    setLoading(false);
    setError(loadError.message || "Unable to load this PDF document.");
  }, []);

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (!numPages) {
        return;
      }
      const boundedPage = Math.min(Math.max(1, nextPage), numPages);
      setViewerPage(boundedPage);
    },
    [numPages, setViewerPage],
  );

  const handleZoomChange = useCallback(
    (nextZoom: number) => {
      const boundedZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
      setViewerZoom(Number(boundedZoom.toFixed(2)));
    },
    [setViewerZoom],
  );

  if (!document) {
    return (
      <div
        className={cn(
          "flex min-h-0 flex-1 items-center justify-center bg-muted/20",
          className,
        )}
      >
        <div className="max-w-sm px-6 text-center">
          <div className="mx-auto flex size-14 items-center justify-center rounded-2xl border border-border bg-background">
            <FileText className="size-7 text-muted-foreground" />
          </div>
          <h2 className="mt-4 text-sm font-semibold">No document selected</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Select a processed PDF from the document list to open it here.
          </p>
        </div>
      </div>
    );
  }

  if (document.status !== "ready") {
    return (
      <div
        className={cn(
          "flex min-h-0 flex-1 items-center justify-center bg-muted/20",
          className,
        )}
      >
        <div className="max-w-sm px-6 text-center">
          {document.status === "processing" ? (
            <LoaderCircle className="mx-auto size-8 animate-spin text-muted-foreground" />
          ) : (
            <FileText className="mx-auto size-8 text-destructive" />
          )}
          <h2 className="mt-4 text-sm font-semibold">
            {document.status === "processing"
              ? "Processing document"
              : "Document processing failed"}
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {document.status === "processing"
              ? "The document will become available after processing finishes."
              : (document.error_message ??
                "This document could not be processed.")}
          </p>
        </div>
      </div>
    );
  }

  if (!document.storage_url) {
    return (
      <div
        className={cn(
          "flex min-h-0 flex-1 items-center justify-center bg-muted/20",
          className,
        )}
      >
        <div className="max-w-sm px-6 text-center">
          <FileText className="size-8 text-muted-foreground" />
          <h2 className="mt-4 text-sm font-semibold">PDF unavailable</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            This document does not currently have a readable PDF source.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/20",
        className,
      )}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-2 sm:px-3">
        <div className="flex min-w-0 items-center gap-1">
          <button
            type="button"
            aria-label="Previous page"
            disabled={pageNumber <= 1}
            onClick={() => handlePageChange(pageNumber - 1)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          >
            <ChevronLeft className="size-4" />
          </button>

          <div className="flex h-8 items-center gap-1 rounded-md border border-border bg-background px-2 text-xs">
            <input
              type="number"
              min={1}
              max={numPages ?? undefined}
              value={pageNumber}
              aria-label="Page number"
              onChange={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) {
                  handlePageChange(value);
                }
              }}
              className="w-10 bg-transparent text-center outline-none"
            />
            <span className="text-muted-foreground">/</span>
            <span className="min-w-5 text-center text-muted-foreground">
              {numPages ?? "—"}
            </span>
          </div>

          <button
            type="button"
            aria-label="Next page"
            disabled={numPages === null || pageNumber >= numPages}
            onClick={() => handlePageChange(pageNumber + 1)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Zoom out"
            disabled={viewerZoom <= MIN_ZOOM}
            onClick={() => handleZoomChange(viewerZoom - ZOOM_STEP)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          >
            <ZoomOut className="size-4" />
          </button>

          <span
            aria-label="Current zoom"
            className="hidden min-w-12 text-center text-xs text-muted-foreground sm:block"
          >
            {Math.round(viewerZoom * 100)}%
          </span>

          <button
            type="button"
            aria-label="Zoom in"
            disabled={viewerZoom >= MAX_ZOOM}
            onClick={() => handleZoomChange(viewerZoom + ZOOM_STEP)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          >
            <ZoomIn className="size-4" />
          </button>

          <button
            type="button"
            aria-label="Reset PDF view"
            onClick={() => resetViewer()}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <RotateCcw className="size-4" />
          </button>
        </div>
      </div>

      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto">
        <div className="flex min-h-full justify-center p-4 sm:p-6">
          <PdfDocument
            key={document.id}
            file={document.storage_url}
            onLoadSuccess={handleLoadSuccess}
            onLoadError={handleLoadError}
            onLoadStart={() => {
              setLoading(true);
              setError(null);
            }}
            loading={
              <div className="flex min-h-[60vh] items-center justify-center">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  Loading PDF...
                </div>
              </div>
            }
            error={null}
            className="flex justify-center"
          >
            {!error && (
              <Page
                pageNumber={pageNumber}
                width={pageWidth}
                scale={viewerZoom}
                renderAnnotationLayer
                renderTextLayer
                loading={
                  <div className="flex min-h-[60vh] items-center justify-center">
                    <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
                  </div>
                }
              />
            )}
          </PdfDocument>

          {error && (
            <div className="flex min-h-[60vh] max-w-sm flex-col items-center justify-center px-6 text-center">
              <FileText className="size-8 text-destructive" />
              <h2 className="mt-4 text-sm font-semibold">Unable to load PDF</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {error}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
