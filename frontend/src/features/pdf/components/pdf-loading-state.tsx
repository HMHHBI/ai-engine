"use client";

export function PdfLoadingState() {
  return (
    <div
      className="flex h-full min-h-64 items-center justify-center"
      role="status"
      aria-live="polite"
      data-testid="pdf-loading"
    >
      <div className="flex flex-col items-center gap-3">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden="true"
        />
        <p className="text-sm text-muted-foreground">
          Loading PDF…
        </p>
      </div>
    </div>
  );
}
