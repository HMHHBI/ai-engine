import React from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  Loader2,
  Upload,
} from "lucide-react";

import type { DocumentStatus } from "@/types/api";

interface DocumentStatusBadgeProps {
  status: DocumentStatus;
  className?: string;
  onRetry?: () => void;
  retryDisabled?: boolean;
}

export function DocumentStatusBadge({
  status,
  className = "",
  onRetry,
  retryDisabled = false,
}: DocumentStatusBadgeProps) {
  switch (status) {
    case "uploading":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-600 dark:text-blue-400 ${className}`}
          data-testid="status-badge-uploading"
        >
          <Upload
            className="h-3 w-3"
            aria-hidden="true"
          />
          Uploading
        </span>
      );

    case "extracting":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 ${className}`}
          data-testid="status-badge-extracting"
        >
          <Loader2
            className="h-3 w-3 animate-spin"
            aria-hidden="true"
          />
          Extracting Text
        </span>
      );

    case "indexing":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 ${className}`}
          data-testid="status-badge-indexing"
        >
          <Loader2
            className="h-3 w-3 animate-spin"
            aria-hidden="true"
          />
          Indexing Evidence
        </span>
      );

    case "processing":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 ${className}`}
          data-testid="status-badge-processing"
        >
          <Loader2
            className="h-3 w-3 animate-spin"
            aria-hidden="true"
          />
          Preparing Document
        </span>
      );

    case "ready":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 ${className}`}
          data-testid="status-badge-ready"
        >
          <CheckCircle2
            className="h-3 w-3"
            aria-hidden="true"
          />
          Ready
        </span>
      );

    case "failed":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-rose-500/20 bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-600 dark:text-rose-400 ${className}`}
          data-testid="status-badge-failed"
        >
          <AlertCircle
            className="h-3 w-3"
            aria-hidden="true"
          />
          Failed

          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={retryDisabled}
              className="ml-0.5 inline-flex items-center rounded px-1 py-0.5 font-semibold underline underline-offset-2 transition-colors hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:text-rose-300"
              aria-label="Retry document preparation"
            >
              Retry
            </button>
          )}
        </span>
      );

    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground ${className}`}
        >
          <FileSearch
            className="h-3 w-3"
            aria-hidden="true"
          />
          Preparing
        </span>
      );
  }
}
