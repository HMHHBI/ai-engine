import React from "react";
import type { Document } from "@/types/api";
import { FileText, Pencil, Trash2 } from "lucide-react";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import { formatFileSize } from "../document-utils";

interface DocumentListItemProps {
  document: Document;
  isSelected?: boolean;
  onSelect?: (document: Document) => void;
  onEdit?: (document: Document) => void;
  onDelete?: (document: Document) => void;
}

export function DocumentListItem({
  document,
  isSelected = false,
  onSelect,
  onEdit,
  onDelete,
}: DocumentListItemProps) {
  const isSelectable = document.status === "ready";

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

  const handleSelect = (): void => {
    if (!isSelectable) return;
    onSelect?.(document);
  };

  return (
    <div
      role="button"
      tabIndex={isSelectable ? 0 : -1}
      aria-disabled={!isSelectable}
      aria-pressed={isSelected}
      onClick={handleSelect}
      onKeyDown={(event) => {
        if (!isSelectable) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handleSelect();
        }
      }}
      className={`group w-full text-left p-3 rounded-xl border transition-all ${
        isSelectable ? "cursor-pointer" : "cursor-not-allowed opacity-70"
      } ${
        isSelected
          ? "border-blue-500/40 bg-blue-50/50 dark:bg-blue-950/20 shadow-sm"
          : "border-zinc-200 dark:border-zinc-800/80 bg-white dark:bg-zinc-900/40 hover:border-zinc-300 dark:hover:border-zinc-700"
      }`}
      data-testid={`document-item-${document.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="p-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 mt-0.5 shrink-0">
            <FileText className="w-4 h-4" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
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

            {!isSelectable && (
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-1">
                {document.status === "processing"
                  ? "Processing — selection unavailable"
                  : "Processing failed — selection unavailable"}
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={`Edit ${document.filename}`}
            disabled={document.status === "processing"}
            onClick={(event) => {
              event.stopPropagation();
              onEdit?.(document);
            }}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 transition-colors"
          >
            <Pencil className="h-4 w-4" />
          </button>

          <button
            type="button"
            aria-label={`Delete ${document.filename}`}
            onClick={(event) => {
              event.stopPropagation();
              onDelete?.(document);
            }}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-red-600 dark:hover:bg-zinc-800 dark:hover:text-red-400 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
