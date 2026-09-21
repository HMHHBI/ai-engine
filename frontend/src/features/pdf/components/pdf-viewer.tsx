"use client";

import { useEffect, useRef, useState } from "react";
import { Document, pdfjs } from "react-pdf";
import { PdfErrorState } from "@/features/pdf/components/pdf-error-state";
import { PdfLoadingState } from "@/features/pdf/components/pdf-loading-state";
import { PdfPage } from "@/features/pdf/components/pdf-page";
import { PdfToolbar } from "@/features/pdf/components/pdf-toolbar";
import { usePdfDocument } from "@/features/pdf/hooks/use-pdf-document";
import {
  calculateFitHeightScale,
  calculateFitWidthScale,
  clampPage,
  resetZoom,
  zoomIn,
  zoomOut,
} from "@/features/pdf/utils/pdf-viewer-utils";
import type { PdfViewerProps } from "@/features/pdf/types/pdf";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

interface PdfViewerLoadedProps {
  objectUrl: string;
  documentId: number;
  navigationTarget?: PdfNavigationTarget | null;
}

function PdfViewerLoaded({
  objectUrl,
  documentId,
  navigationTarget,
}: PdfViewerLoadedProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [pageDimensions, setPageDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const viewerContainerRef = useRef<HTMLDivElement | null>(null);
  const lastNavigationRequestIdRef = useRef<number | null>(null);

  const goToPage = (page: number) => {
    setCurrentPage((current) => clampPage(page, numPages || current));
  };

  useEffect(() => {
    if (!navigationTarget || numPages <= 0) {
      return;
    }

    if (navigationTarget.documentId !== documentId) {
      return;
    }

    if (lastNavigationRequestIdRef.current === navigationTarget.requestId) {
      return;
    }

    lastNavigationRequestIdRef.current = navigationTarget.requestId;

    setCurrentPage(clampPage(navigationTarget.pageNumber, numPages));
  }, [navigationTarget, documentId, numPages]);

  const handleFitWidth = () => {
    if (!pageDimensions || !viewerContainerRef.current) {
      return;
    }
    const container = viewerContainerRef.current;
    setScale(calculateFitWidthScale(pageDimensions.width, container.clientWidth - 32));
  };

  const handleFitHeight = () => {
    if (!pageDimensions || !viewerContainerRef.current) {
      return;
    }
    const container = viewerContainerRef.current;
    setScale(calculateFitHeightScale(pageDimensions.height, container.clientHeight - 32));
  };

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="pdf-viewer">
      <PdfToolbar
        currentPage={currentPage}
        numPages={numPages}
        scale={scale}
        onPreviousPage={() => goToPage(currentPage - 1)}
        onNextPage={() => goToPage(currentPage + 1)}
        onZoomOut={() => setScale((value) => zoomOut(value))}
        onZoomIn={() => setScale((value) => zoomIn(value))}
        onResetZoom={() => setScale(resetZoom())}
        onFitWidth={handleFitWidth}
        onFitHeight={handleFitHeight}
      />

      <div
        ref={viewerContainerRef}
        className="min-h-0 flex-1 overflow-auto p-4"
      >
        <Document
          file={objectUrl}
          loading={<PdfLoadingState />}
          error={
            <PdfErrorState
              error={{
                code: "INVALID_PDF",
                message: "The PDF could not be parsed or rendered.",
              }}
            />
          }
          onLoadSuccess={({ numPages: loadedPages }) => {
            setNumPages(loadedPages);
            setCurrentPage((page) => clampPage(page, loadedPages));
          }}
        >
          {numPages > 0 && (
            <PdfPage
              pageNumber={clampPage(currentPage, numPages)}
              scale={scale}
              onLoadSuccess={(page) => {
                const viewport = page.getViewport({ scale: 1 });
                setPageDimensions({
                  width: viewport.width,
                  height: viewport.height,
                });
              }}
            />
          )}
        </Document>
      </div>
    </div>
  );
}

export function PdfViewer({ documentId, navigationTarget }: PdfViewerProps) {
  const { status, objectUrl, error } = usePdfDocument(documentId);

  if (documentId === null) {
    return (
      <div
        className="flex h-full items-center justify-center"
        data-testid="pdf-viewer-empty"
      >
        <p className="text-sm text-muted-foreground">
          Select a document to view it.
        </p>
      </div>
    );
  }

  if (status === "loading") {
    return <PdfLoadingState />;
  }

  if (status === "error" || !objectUrl) {
    return (
      <PdfErrorState
        error={
          error ?? {
            code: "UNKNOWN",
            message: "The PDF could not be loaded.",
          }
        }
      />
    );
  }

  return (
    <PdfViewerLoaded
      key={documentId}
      objectUrl={objectUrl}
      documentId={documentId}
      navigationTarget={navigationTarget}
    />
  );
}
