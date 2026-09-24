import React from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  FileText,
  Loader2,
  Upload,
} from "lucide-react";

import type { DocumentStatus } from "@/types/api";
import type { DocumentPreparationStage } from "@/types/research-session";

interface DocumentStatusBadgeProps {
  status: DocumentStatus | DocumentPreparationStage;
  className?: string;
  onRetry?: () => void;
}

type BadgeStage = DocumentPreparationStage;

function normalizeStage(
  status: DocumentStatus | DocumentPreparationStage,
): BadgeStage {
  if (status === "processing") {
    return "indexing";
  }

  return status;
}

export function DocumentStatusBadge({
  status,
  className = "",
  onRetry,
}: DocumentStatusBadgeProps) {
  const stage = normalizeStage(status);

  switch (stage) {
    case "uploading":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-600 dark:text-blue-400 ${className}`}
          data-testid="status-badge-uploading"
        >
          <Upload className="h-3 w-3" />
          Uploading
        </span>
      );

    case "extracting":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 ${className}`}
          data-testid="status-badge-extracting"
        >
          <FileText className="h-3 w-3" />
          Extracting Text
        </span>
      );

    case "indexing":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 ${className}`}
          data-testid="status-badge-indexing"
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          Indexing Evidence
        </span>
      );

    case "ready":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 ${className}`}
          data-testid="status-badge-ready"
        >
          <CheckCircle2 className="h-3 w-3" />
          Ready
        </span>
      );

    case "failed":
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-rose-500/20 bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-600 dark:text-rose-400 ${className}`}
          data-testid="status-badge-failed"
        >
          <AlertCircle className="h-3 w-3" />
          Failed
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="ml-0.5 inline-flex items-center rounded px-1 py-0.5 font-semibold underline underline-offset-2 transition-colors hover:text-rose-700 dark:hover:text-rose-300"
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
          <FileSearch className="h-3 w-3" />
          Preparing
        </span>
      );
  }
}
