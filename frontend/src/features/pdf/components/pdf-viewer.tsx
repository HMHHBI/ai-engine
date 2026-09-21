"use client";

import { useState } from "react";
import { Document, pdfjs } from "react-pdf";
import { PdfErrorState } from "@/features/pdf/components/pdf-error-state";
import { PdfLoadingState } from "@/features/pdf/components/pdf-loading-state";
import { PdfPage } from "@/features/pdf/components/pdf-page";
import { PdfToolbar } from "@/features/pdf/components/pdf-toolbar";
import { usePdfDocument } from "@/features/pdf/hooks/use-pdf-document";
import {
  clampPage,
  MIN_SCALE,
  MAX_SCALE,
  SCALE_STEP,
} from "@/features/pdf/utils/pdf-viewer-utils";
import type { PdfViewerProps } from "@/features/pdf/types/pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

function PdfViewerLoaded({
  objectUrl,
}: {
  objectUrl: string;
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1);

  const goToPage = (page: number) => {
    setCurrentPage((current) => clampPage(page, numPages || current));
  };

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="pdf-viewer">
      <PdfToolbar
        currentPage={currentPage}
        numPages={numPages}
        scale={scale}
        onPreviousPage={() => {
          goToPage(currentPage - 1);
        }}
        onNextPage={() => {
          goToPage(currentPage + 1);
        }}
        onZoomOut={() => {
          setScale((value) =>
            Math.max(MIN_SCALE, Number((value - SCALE_STEP).toFixed(2))),
          );
        }}
        onZoomIn={() => {
          setScale((value) =>
            Math.min(MAX_SCALE, Number((value + SCALE_STEP).toFixed(2))),
          );
        }}
      />

      <div className="min-h-0 flex-1 overflow-auto p-4">
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
            <PdfPage pageNumber={clampPage(currentPage, numPages)} scale={scale} />
          )}
        </Document>
      </div>
    </div>
  );
}

export function PdfViewer({ documentId }: PdfViewerProps) {
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

  return <PdfViewerLoaded key={documentId} objectUrl={objectUrl} />;
}
