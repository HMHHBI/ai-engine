"use client";

import { Minus, Plus } from "lucide-react";
import type { PdfToolbarProps } from "@/features/pdf/types/pdf";

export function PdfToolbar({
  currentPage,
  numPages,
  scale,
  onPreviousPage,
  onNextPage,
  onZoomOut,
  onZoomIn,
}: PdfToolbarProps) {
  return (
    <div
      className="flex items-center justify-between gap-3 border-b px-3 py-2"
      data-testid="pdf-toolbar"
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPreviousPage}
          disabled={currentPage <= 1}
          aria-label="Previous page"
          data-testid="pdf-prev"
          className="rounded border px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>

        <span
          className="min-w-20 text-center text-sm"
          aria-label="Current page"
          data-testid="pdf-current-page"
        >
          {currentPage} / {numPages}
        </span>

        <button
          type="button"
          onClick={onNextPage}
          disabled={currentPage >= numPages}
          aria-label="Next page"
          data-testid="pdf-next"
          className="rounded border px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onZoomOut}
          disabled={scale <= 0.5}
          aria-label="Zoom out"
          data-testid="pdf-zoom-out"
          className="rounded border p-1.5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Minus className="h-4 w-4" aria-hidden="true" />
        </button>

        <span className="min-w-14 text-center text-sm">
          {Math.round(scale * 100)}%
        </span>

        <button
          type="button"
          onClick={onZoomIn}
          disabled={scale >= 3}
          aria-label="Zoom in"
          data-testid="pdf-zoom-in"
          className="rounded border p-1.5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
