"use client";

import { Page } from "react-pdf";
import type { PdfPageProps } from "@/features/pdf/types/pdf";

export function PdfPage({
  pageNumber,
  scale,
  width,
  onRenderSuccess,
  onRenderError,
}: PdfPageProps) {
  return (
    <div
      className="flex justify-center"
      data-testid="pdf-page"
      data-page-number={pageNumber}
    >
      <Page
        pageNumber={pageNumber}
        scale={width ? undefined : scale}
        width={width}
        renderAnnotationLayer
        renderTextLayer
        onRenderSuccess={onRenderSuccess}
        onRenderError={onRenderError}
      />
    </div>
  );
}
