import React from "react";
import type { DocumentStatus } from "@/types/api";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface DocumentStatusBadgeProps {
  status: DocumentStatus;
  className?: string;
}

export function DocumentStatusBadge({
  status,
  className = "",
}: DocumentStatusBadgeProps) {
  switch (status) {
    case "ready":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 ${className}`}
          data-testid="status-badge-ready"
        >
          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
          Ready
        </span>
      );
    case "processing":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 ${className}`}
          data-testid="status-badge-processing"
        >
          <Loader2 className="w-3 h-3 animate-spin text-amber-500" />
          Processing
        </span>
      );
    case "failed":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 ${className}`}
          data-testid="status-badge-failed"
        >
          <AlertCircle className="w-3 h-3 text-rose-500" />
          Failed
        </span>
      );
    default:
      return null;
  }
}
