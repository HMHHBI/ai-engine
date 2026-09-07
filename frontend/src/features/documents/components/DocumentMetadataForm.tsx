"use client";

import React, { useState } from "react";
import { X, Loader2 } from "lucide-react";
import type { Document } from "@/types/api";
import { updateDocument } from "../document-actions";
import { useDocumentStore } from "../document-store";

interface DocumentMetadataFormProps {
  document: Document;
  isOpen: boolean;
  onClose: () => void;
}

export function DocumentMetadataForm({
  document,
  isOpen,
  onClose,
}: DocumentMetadataFormProps) {
  const [filename, setFilename] = useState(document.filename);
  const [pageCount, setPageCount] = useState(
    document.page_count !== null ? String(document.page_count) : "",
  );
  const [error, setError] = useState<string | null>(null);

  const isMutating = useDocumentStore(
    (state) => state.mutatingDocumentIds[document.id] ?? false,
  );

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = filename.trim();
    if (!trimmed) {
      setError("Filename cannot be empty.");
      return;
    }

    const parsedPages =
      pageCount.trim() === "" ? null : parseInt(pageCount, 10);
    if (parsedPages !== null && (isNaN(parsedPages) || parsedPages < 0)) {
      setError("Page count must be a positive integer.");
      return;
    }

    try {
      setError(null);
      await updateDocument(document.id, {
        filename: trimmed,
        page_count: parsedPages,
      });
      onClose();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to update document.",
      );
    }
  };

  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center p-4"
      data-testid="document-metadata-dialog"
    >
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs"
        onClick={isMutating ? undefined : onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-metadata-title"
        className="relative z-10 w-full max-w-md rounded-xl bg-white p-5 shadow-2xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800"
      >
        <div className="flex items-center justify-between pb-3 border-b border-zinc-100 dark:border-zinc-800">
          <h2
            id="document-metadata-title"
            className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
          >
            Edit Document Metadata
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isMutating}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label
              htmlFor="edit-doc-filename"
              className="block text-xs font-medium text-zinc-700 dark:text-zinc-300"
            >
              Filename
            </label>
            <input
              id="edit-doc-filename"
              type="text"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              disabled={isMutating}
              className="mt-1 block w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
              required
            />
          </div>

          <div>
            <label
              htmlFor="edit-doc-pages"
              className="block text-xs font-medium text-zinc-700 dark:text-zinc-300"
            >
              Page Count
            </label>
            <input
              id="edit-doc-pages"
              type="number"
              min="0"
              value={pageCount}
              onChange={(e) => setPageCount(e.target.value)}
              disabled={isMutating}
              className="mt-1 block w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
          </div>

          {error && (
            <div
              role="alert"
              className="p-2.5 rounded-lg bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 text-xs text-rose-700 dark:text-rose-400"
            >
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isMutating}
              className="rounded-lg px-3 py-2 text-xs font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isMutating}
              className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3.5 py-2 text-xs font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 disabled:opacity-50"
            >
              {isMutating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
