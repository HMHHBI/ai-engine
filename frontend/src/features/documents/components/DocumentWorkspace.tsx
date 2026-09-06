import React, { useEffect, useRef, useMemo } from "react";
import { X, Upload, FileText, AlertTriangle } from "lucide-react";
import { useDocumentStore } from "../document-store";
import { loadDocuments, selectDocument } from "../document-actions";
import { DocumentList } from "./DocumentList";
import { DocumentEmptyState } from "./DocumentEmptyState";
import type { Document } from "@/types/api";

interface DocumentWorkspaceProps {
  chatId: number;
  isOpen: boolean;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLElement | null>;
}

const EMPTY_DOCUMENTS: Document[] = [];

export function DocumentWorkspace({
  chatId,
  isOpen,
  onClose,
  triggerRef,
}: DocumentWorkspaceProps) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Stable direct references from store
  const documentsByChat = useDocumentStore((state) => state.documentsByChat);
  const selectedDocumentIdByChat = useDocumentStore(
    (state) => state.selectedDocumentIdByChat,
  );
  const loadingByChat = useDocumentStore((state) => state.loadingByChat);
  const errorByChat = useDocumentStore((state) => state.errorByChat);

  const documents = useMemo(
    () => documentsByChat[chatId] ?? EMPTY_DOCUMENTS,
    [documentsByChat, chatId],
  );
  const selectedDocumentId = selectedDocumentIdByChat[chatId] ?? null;
  const isLoading = loadingByChat[chatId] ?? false;
  const error = errorByChat[chatId] ?? null;

  useEffect(() => {
    if (isOpen && chatId) {
      loadDocuments(chatId).catch(() => {});
    }
  }, [isOpen, chatId]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        triggerRef?.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    drawerRef.current?.focus();

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose, triggerRef]);

  if (!isOpen) return null;

  const handleUploadTrigger = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (
      file.type !== "application/pdf" &&
      !file.name.toLowerCase().endsWith(".pdf")
    ) {
      alert("Only PDF documents are supported.");
      e.target.value = "";
      return;
    }
    e.target.value = "";
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      data-testid="document-workspace"
    >
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
        data-testid="document-workspace-backdrop"
      />

      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-workspace-title"
        tabIndex={-1}
        className="relative z-50 w-full sm:w-100 h-full bg-white dark:bg-zinc-950 border-l border-zinc-200 dark:border-zinc-800 shadow-2xl flex flex-col focus:outline-none"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h2
                id="document-workspace-title"
                className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
              >
                Documents
              </h2>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {documents.length} document{documents.length === 1 ? "" : "s"}{" "}
                attached
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              onClose();
              triggerRef?.current?.focus();
            }}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            aria-label="Close document workspace"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 border-b border-zinc-100 dark:border-zinc-900">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={handleFileSelected}
            data-testid="document-upload-input"
          />
          <button
            onClick={handleUploadTrigger}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium text-white bg-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-zinc-200 rounded-lg shadow-sm transition-colors"
            data-testid="upload-pdf-button"
          >
            <Upload className="w-3.5 h-3.5" />
            Upload PDF
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div
              className="p-3 mb-4 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-start gap-2.5 text-xs text-rose-700 dark:text-rose-400"
              data-testid="document-workspace-error"
            >
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {isLoading ? (
            <div className="space-y-3" data-testid="document-loading-skeleton">
              <div className="h-16 rounded-xl bg-zinc-100 dark:bg-zinc-900 animate-pulse" />
              <div className="h-16 rounded-xl bg-zinc-100 dark:bg-zinc-900 animate-pulse" />
              <div className="h-16 rounded-xl bg-zinc-100 dark:bg-zinc-900 animate-pulse" />
            </div>
          ) : documents.length === 0 ? (
            <DocumentEmptyState onUploadClick={handleUploadTrigger} />
          ) : (
            <DocumentList
              documents={documents}
              selectedDocumentId={selectedDocumentId}
              onSelectDocument={(doc) => selectDocument(chatId, doc.id)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
