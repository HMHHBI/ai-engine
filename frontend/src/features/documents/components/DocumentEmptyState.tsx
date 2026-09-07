import React from "react";
import { FileText, Upload } from "lucide-react";

interface DocumentEmptyStateProps {
  onUploadClick?: () => void;
}

export function DocumentEmptyState({ onUploadClick }: DocumentEmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center p-8 text-center rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30"
      data-testid="document-empty-state"
    >
      <div className="w-12 h-12 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center mb-3">
        <FileText className="w-6 h-6 text-zinc-400" />
      </div>
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        No documents yet
      </h3>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-60">
        Upload a PDF to give this chat document context.
      </p>
      {onUploadClick && (
        <button
          onClick={onUploadClick}
          className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-zinc-200 rounded-lg shadow-sm transition-colors"
        >
          <Upload className="w-3.5 h-3.5" />
          Upload PDF
        </button>
      )}
    </div>
  );
}
