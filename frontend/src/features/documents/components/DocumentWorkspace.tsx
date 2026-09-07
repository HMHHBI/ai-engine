"use client";

import React, { useEffect, useRef, useMemo, useState } from "react";
import { X, FileText, AlertTriangle } from "lucide-react";
import { useDocumentStore } from "../document-store";
import {
  loadDocuments,
  selectDocument,
  deleteDocument,
} from "../document-actions";
import { DocumentList } from "./DocumentList";
import { DocumentEmptyState } from "./DocumentEmptyState";
import { DocumentUpload } from "./DocumentUpload";
import { DocumentDeleteDialog } from "./DocumentDeleteDialog";
import { DocumentMetadataForm } from "./DocumentMetadataForm";
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

  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(
    null,
  );
  const [editingDocumentId, setEditingDocumentId] = useState<number | null>(
    null,
  );

  const documentsByChat = useDocumentStore((state) => state.documentsByChat);
  const selectedDocumentIdByChat = useDocumentStore(
    (state) => state.selectedDocumentIdByChat,
  );
  const loadingByChat = useDocumentStore((state) => state.loadingByChat);
  const mutatingDocumentIds = useDocumentStore(
    (state) => state.mutatingDocumentIds,
  );
  const errorByChat = useDocumentStore((state) => state.errorByChat);

  const documents = useMemo(
    () => documentsByChat[chatId] ?? EMPTY_DOCUMENTS,
    [documentsByChat, chatId],
  );
  const selectedDocumentId = selectedDocumentIdByChat[chatId] ?? null;
  const isLoading = loadingByChat[chatId] ?? false;
  const error = errorByChat[chatId] ?? null;

  const deletingDocument = useMemo(
    () => documents.find((doc) => doc.id === deletingDocumentId) ?? null,
    [documents, deletingDocumentId],
  );

  const editingDocument = useMemo(
    () => documents.find((doc) => doc.id === editingDocumentId) ?? null,
    [documents, editingDocumentId],
  );

  useEffect(() => {
    if (isOpen && chatId) {
      loadDocuments(chatId).catch(() => {});
    }
  }, [isOpen, chatId]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !deletingDocumentId && !editingDocumentId) {
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
  }, [isOpen, onClose, triggerRef, deletingDocumentId, editingDocumentId]);

  if (!isOpen) return null;

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

        {/* Upload Action Area */}
        <div className="p-4 border-b border-zinc-100 dark:border-zinc-900">
          <DocumentUpload chatId={chatId} />
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {error && (
            <div
              className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-start gap-2.5 text-xs text-rose-700 dark:text-rose-400"
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
            <DocumentEmptyState />
          ) : (
            <DocumentList
              documents={documents}
              selectedDocumentId={selectedDocumentId}
              onSelectDocument={(doc) => selectDocument(chatId, doc.id)}
              onEditDocument={(doc) => setEditingDocumentId(doc.id)}
              onDeleteDocument={(doc) => setDeletingDocumentId(doc.id)}
            />
          )}
        </div>
      </div>

      {editingDocument && (
        <DocumentMetadataForm
          document={editingDocument}
          isOpen={!!editingDocument}
          onClose={() => setEditingDocumentId(null)}
        />
      )}

      {deletingDocument && (
        <DocumentDeleteDialog
          filename={deletingDocument.filename}
          deleting={!!mutatingDocumentIds[deletingDocument.id]}
          onCancel={() => setDeletingDocumentId(null)}
          onConfirm={async () => {
            await deleteDocument(chatId, deletingDocument.id);
            setDeletingDocumentId(null);
          }}
        />
      )}
    </div>
  );
}
