import React from "react";
import type { Document } from "@/types/api";
import {
  FileText,
  Pencil,
  Trash2,
} from "lucide-react";
import {
  DocumentStatusBadge,
} from "./DocumentStatusBadge";
import {
  formatFileSize,
  getDocumentLifecycleLabel,
} from "../document-utils";

interface DocumentListItemProps {
  document: Document;
  isSelected?: boolean;
  onSelect?: (document: Document) => void;
  onEdit?: (document: Document) => void;
  onDelete?: (document: Document) => void;
  onRetry?: (document: Document) => void;
  retryDisabled?: boolean;
}

export function DocumentListItem({
  document,
  isSelected = false,
  onSelect,
  onEdit,
  onDelete,
  onRetry,
  retryDisabled = false,
}: DocumentListItemProps) {
  const isSelectable =
    document.status === "ready";

  const metadataParts: string[] = [];

  metadataParts.push(
    document.mime_type === "application/pdf"
      ? "PDF"
      : document.mime_type
          .split("/")[1]
          ?.toUpperCase() ?? "DOC",
  );

  if (
    document.page_count !== null &&
    document.page_count !== undefined
  ) {
    metadataParts.push(
      `${document.page_count} page${
        document.page_count === 1
          ? ""
          : "s"
      }`,
    );
  }

  const formattedSize =
    formatFileSize(
      document.file_size,
    );

  if (formattedSize) {
    metadataParts.push(
      formattedSize,
    );
  }

  const handleSelect = (): void => {
    if (!isSelectable) {
      return;
    }

    onSelect?.(document);
  };

  return (
    <div
      role="button"
      tabIndex={
        isSelectable ? 0 : -1
      }
      aria-disabled={!isSelectable}
      aria-pressed={isSelected}
      onClick={handleSelect}
      onKeyDown={(event) => {
        if (!isSelectable) {
          return;
        }

        if (
          event.key === "Enter" ||
          event.key === " "
        ) {
          event.preventDefault();
          handleSelect();
        }
      }}
      className={`group w-full rounded-xl border p-3 text-left transition-all ${
        isSelectable
          ? "cursor-pointer"
          : "cursor-not-allowed opacity-70"
      } ${
        isSelected
          ? "border-blue-500/40 bg-blue-50/50 shadow-sm dark:bg-blue-950/20"
          : "border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800/80 dark:bg-zinc-900/40 dark:hover:border-zinc-700"
      }`}
      data-testid={`document-item-${document.id}`}
      data-doc-id={document.id}
    >
      <div
        data-testid="document-list-item"
        data-doc-id={document.id}
        className="flex items-start justify-between gap-3"
      >
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="mt-0.5 shrink-0 rounded-lg bg-zinc-100 p-2 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            <FileText
              className="h-4 w-4"
              aria-hidden="true"
            />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100"
                title={document.filename}
              >
                {document.filename}
              </span>

              <DocumentStatusBadge
                status={document.status}
                className="shrink-0"
                onRetry={
                  document.status === "failed"
                    ? () => onRetry?.(document)
                    : undefined
                }
                retryDisabled={
                  retryDisabled
                }
              />
            </div>

            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
              {metadataParts.join(" · ")}
            </p>

            {document.status !== "ready" && (
              <p
                className="mt-1 text-[11px] text-zinc-400 dark:text-zinc-500"
                data-testid={`document-lifecycle-${document.id}`}
              >
                {document.status === "failed"
                  ? "Processing failed. Retry preparation to make this document available."
                  : getDocumentLifecycleLabel(
                      document.status,
                    )}
              </p>
            )}

            {document.status ===
              "failed" &&
              document.error_message && (
                <p
                  className="mt-1 line-clamp-2 text-[11px] text-rose-500 dark:text-rose-400"
                  data-testid={`document-error-${document.id}`}
                >
                  {document.error_message}
                </p>
              )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={`Edit ${document.filename}`}
            disabled={
              document.status !== "ready"
            }
            onClick={(event) => {
              event.stopPropagation();
              onEdit?.(document);
            }}
            className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          >
            <Pencil
              className="h-4 w-4"
              aria-hidden="true"
            />
          </button>

          <button
            type="button"
            aria-label={`Delete ${document.filename}`}
            onClick={(event) => {
              event.stopPropagation();
              onDelete?.(document);
            }}
            className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-red-600 dark:hover:bg-zinc-800 dark:hover:text-red-400"
          >
            <Trash2
              className="h-4 w-4"
              aria-hidden="true"
            />
          </button>
        </div>
      </div>
    </div>
  );
}
