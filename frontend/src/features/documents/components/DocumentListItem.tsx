import React from "react";
import type { Document } from "@/types/api";
import { FileText } from "lucide-react";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import { formatFileSize } from "../document-utils";

interface DocumentListItemProps {
  document: Document;
  isSelected?: boolean;
  onSelect?: (document: Document) => void;
}

export function DocumentListItem({
  document,
  isSelected = false,
  onSelect,
}: DocumentListItemProps) {
  const metadataParts: string[] = [];

  if (document.mime_type === "application/pdf") {
    metadataParts.push("PDF");
  } else {
    metadataParts.push(
      document.mime_type.split("/")[1]?.toUpperCase() ?? "DOC",
    );
  }

  if (document.page_count !== null && document.page_count !== undefined) {
    metadataParts.push(
      `${document.page_count} page${document.page_count === 1 ? "" : "s"}`,
    );
  }

  const formattedSize = formatFileSize(document.file_size);
  if (formattedSize) {
    metadataParts.push(formattedSize);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(document)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(document);
        }
      }}
      className={`group w-full text-left p-3 rounded-xl border transition-all cursor-pointer ${
        isSelected
          ? "border-blue-500/40 bg-blue-50/50 dark:bg-blue-950/20 shadow-sm"
          : "border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/40 hover:border-zinc-300 dark:hover:border-zinc-700"
      }`}
      data-testid={`document-item-${document.id}`}
      aria-pressed={isSelected}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 mt-0.5 shrink-0">
          <FileText className="w-4 h-4" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate"
              title={document.filename}
            >
              {document.filename}
            </span>
            <DocumentStatusBadge
              status={document.status}
              className="shrink-0"
            />
          </div>

          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 flex items-center gap-1.5 flex-wrap">
            {metadataParts.join(" · ")}
          </p>
        </div>
      </div>
    </div>
  );
}
