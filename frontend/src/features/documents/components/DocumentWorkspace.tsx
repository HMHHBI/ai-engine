"use client";

import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  useRouter,
  usePathname,
  useSearchParams,
} from "next/navigation";
import {
  X,
  FileText,
  AlertTriangle,
} from "lucide-react";

import { useDocumentStore } from "../document-store";
import {
  loadDocuments,
  selectDocument,
  deleteDocument,
  retryDocument,
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
  const drawerRef =
    useRef<HTMLDivElement>(null);

  const router = useRouter();
  const pathname = usePathname();
  const searchParams =
    useSearchParams();

  const [
    deletingDocumentId,
    setDeletingDocumentId,
  ] = useState<number | null>(null);

  const [
    editingDocumentId,
    setEditingDocumentId,
  ] = useState<number | null>(null);

  const [
    retryingDocumentId,
    setRetryingDocumentId,
  ] = useState<number | null>(null);

  const documentsByChat =
    useDocumentStore(
      (state) =>
        state.documentsByChat,
    );

  const selectedDocumentIdByChat =
    useDocumentStore(
      (state) =>
        state.selectedDocumentIdByChat,
    );

  const loadingByChat =
    useDocumentStore(
      (state) =>
        state.loadingByChat,
    );

  const mutatingDocumentIds =
    useDocumentStore(
      (state) =>
        state.mutatingDocumentIds,
    );

  const errorByChat =
    useDocumentStore(
      (state) =>
        state.errorByChat,
    );

  const documents = useMemo(
    () =>
      documentsByChat[chatId] ??
      EMPTY_DOCUMENTS,
    [documentsByChat, chatId],
  );

  const selectedDocumentId =
    selectedDocumentIdByChat[
      chatId
    ] ?? null;

  const isLoading =
    loadingByChat[chatId] ??
    false;

  const error =
    errorByChat[chatId] ??
    null;

  const deletingDocument =
    useMemo(
      () =>
        documents.find(
          (doc) =>
            doc.id ===
            deletingDocumentId,
        ) ?? null,
      [
        documents,
        deletingDocumentId,
      ],
    );

  const editingDocument =
    useMemo(
      () =>
        documents.find(
          (doc) =>
            doc.id ===
            editingDocumentId,
        ) ?? null,
      [
        documents,
        editingDocumentId,
      ],
    );

  useEffect(() => {
    if (isOpen && chatId) {
      void loadDocuments(chatId);
    }
  }, [isOpen, chatId]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (
      event: KeyboardEvent,
    ) => {
      if (
        event.key === "Escape" &&
        !deletingDocumentId &&
        !editingDocumentId
      ) {
        event.preventDefault();
        onClose();
        triggerRef?.current?.focus();
      }
    };

    window.addEventListener(
      "keydown",
      handleKeyDown,
    );

    drawerRef.current?.focus();

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [
    isOpen,
    onClose,
    triggerRef,
    deletingDocumentId,
    editingDocumentId,
  ]);

  if (!isOpen) {
    return null;
  }

  const handleSelectDocument = (
    document: Document,
  ) => {
    const isSelected =
      selectedDocumentId ===
      document.id;

    if (
      !selectDocument(
        chatId,
        document.id,
      )
    ) {
      return;
    }

    const params =
      new URLSearchParams(
        searchParams?.toString() ??
          "",
      );

    if (isSelected) {
      params.delete("docId");
    } else {
      params.set(
        "docId",
        String(document.id),
      );
    }

    const query =
      params.toString();

    router.push(
      query
        ? `${pathname}?${query}`
        : pathname,
    );
  };

  const handleRetryDocument =
    async (document: Document) => {
      if (
        retryingDocumentId !==
        null
      ) {
        return;
      }

      setRetryingDocumentId(
        document.id,
      );

      try {
        await retryDocument(
          chatId,
          document.id,
        );
      } catch {
      } finally {
        setRetryingDocumentId(
          null,
        );
      }
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
        className="relative z-50 flex h-full w-full flex-col border-l border-zinc-200 bg-white shadow-2xl focus:outline-none dark:border-zinc-800 dark:bg-zinc-950 sm:w-100"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-zinc-100 p-1.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              <FileText
                className="h-4 w-4"
                aria-hidden="true"
              />
            </div>

            <div>
              <h2
                id="document-workspace-title"
                className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
              >
                Documents
              </h2>

              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {documents.length}{" "}
                document
                {documents.length ===
                1
                  ? ""
                  : "s"}{" "}
                attached
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              onClose();
              triggerRef?.current?.focus();
            }}
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
            aria-label="Close document workspace"
          >
            <X
              className="h-4 w-4"
              aria-hidden="true"
            />
          </button>
        </div>

        <div className="border-b border-zinc-100 p-4 dark:border-zinc-900">
          <DocumentUpload
            chatId={chatId}
          />
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {error && (
            <div
              className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-400"
              data-testid="document-workspace-error"
            >
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>{error}</span>
            </div>
          )}

          {isLoading ? (
            <div
              className="space-y-3"
              data-testid="document-loading-skeleton"
            >
              <div className="h-16 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
              <div className="h-16 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
              <div className="h-16 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
            </div>
          ) : documents.length === 0 ? (
            <DocumentEmptyState />
          ) : (
            <DocumentList
              documents={documents}
              selectedDocumentId={
                selectedDocumentId
              }
              onSelectDocument={
                handleSelectDocument
              }
              onEditDocument={(doc) =>
                setEditingDocumentId(
                  doc.id,
                )
              }
              onDeleteDocument={(doc) =>
                setDeletingDocumentId(
                  doc.id,
                )
              }
              onRetryDocument={
                handleRetryDocument
              }
              retryingDocumentId={
                retryingDocumentId
              }
            />
          )}
        </div>
      </div>

      {editingDocument && (
        <DocumentMetadataForm
          document={
            editingDocument
          }
          isOpen={
            !!editingDocument
          }
          onClose={() =>
            setEditingDocumentId(
              null,
            )
          }
        />
      )}

      {deletingDocument && (
        <DocumentDeleteDialog
          filename={
            deletingDocument.filename
          }
          deleting={
            !!mutatingDocumentIds[
              deletingDocument.id
            ]
          }
          onCancel={() =>
            setDeletingDocumentId(
              null,
            )
          }
          onConfirm={async () => {
            await deleteDocument(
              chatId,
              deletingDocument.id,
            );

            setDeletingDocumentId(
              null,
            );
          }}
        />
      )}
    </div>
  );
}
