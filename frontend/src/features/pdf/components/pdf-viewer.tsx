"use client";

import { useState } from "react";
import { Document, pdfjs } from "react-pdf";
import { PdfErrorState } from "@/features/pdf/components/pdf-error-state";
import { PdfLoadingState } from "@/features/pdf/components/pdf-loading-state";
import { PdfPage } from "@/features/pdf/components/pdf-page";
import { PdfToolbar } from "@/features/pdf/components/pdf-toolbar";
import { usePdfDocument } from "@/features/pdf/hooks/use-pdf-document";
import type { PdfViewerProps } from "@/features/pdf/types/pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

const MIN_SCALE = 0.5;
const MAX_SCALE = 3;
const SCALE_STEP = 0.25;

function PdfViewerLoaded({
  objectUrl,
}: {
  objectUrl: string;
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1);

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="pdf-viewer">
      <PdfToolbar
        currentPage={currentPage}
        numPages={numPages}
        scale={scale}
        onPreviousPage={() => {
          setCurrentPage((page) => Math.max(1, page - 1));
        }}
        onNextPage={() => {
          setCurrentPage((page) => Math.min(numPages, page + 1));
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
            setCurrentPage((page) => Math.min(Math.max(page, 1), loadedPages));
          }}
        >
          {numPages > 0 && (
            <PdfPage pageNumber={currentPage} scale={scale} />
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
