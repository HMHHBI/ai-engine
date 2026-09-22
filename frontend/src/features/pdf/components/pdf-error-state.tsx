"use client";

import type { PdfDocumentError } from "@/features/pdf/types/pdf";

interface PdfErrorStateProps {
  error: PdfDocumentError;
}

export function PdfErrorState({
  error,
}: PdfErrorStateProps) {
  return (
    <div
      className="flex h-full min-h-64 items-center justify-center p-6"
      data-testid="pdf-error"
    >
      <div className="max-w-md text-center">
        <h2 className="text-sm font-semibold">
          Unable to load PDF
        </h2>

        <p className="mt-2 text-sm text-muted-foreground">
          {error.message}
        </p>
      </div>
    </div>
  );
}
