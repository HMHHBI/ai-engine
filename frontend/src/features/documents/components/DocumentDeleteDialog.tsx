"use client";

import React from "react";
import { Loader2 } from "lucide-react";

interface DocumentDeleteDialogProps {
  filename: string;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
}

export function DocumentDeleteDialog({
  filename,
  deleting,
  onCancel,
  onConfirm,
}: DocumentDeleteDialogProps) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center p-4"
      data-testid="document-delete-dialog"
    >
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs"
        onClick={deleting ? undefined : onCancel}
        aria-hidden="true"
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="document-delete-title"
        className="relative z-10 w-full max-w-sm rounded-xl bg-white p-5 shadow-2xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800"
      >
        <h2
          id="document-delete-title"
          className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
        >
          Delete document?
        </h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          Are you sure you want to delete{" "}
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            “{filename}”
          </span>
          ? Vector embeddings associated with this document will be removed.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="rounded-lg px-3 py-2 text-xs font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-rose-700 disabled:opacity-50"
          >
            {deleting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
