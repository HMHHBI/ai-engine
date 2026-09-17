"use client";

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  LoaderCircle,
  Menu,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatArea } from "@/features/chat/components/chat-area";
import { ChatHistoryList } from "@/features/chat/components/chat-history-list";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import {
  deleteDocument,
  loadDocuments,
  selectDocument,
  uploadDocument,
} from "@/features/documents/document-actions";
import { useDocumentStore } from "@/features/documents/document-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useWorkspaceStore } from "@/features/workspace/store/workspace-store";
import type { Document } from "@/types/api";
import { cn } from "@/lib/utils";

interface ResearchWorkspaceProps {
  chatId: number;
}

type MobilePanel = "navigation" | "document" | "chat" | null;

export function ResearchWorkspace({ chatId }: ResearchWorkspaceProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>(null);
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const activeChatId = useChatStore((state) => state.activeChatId);

  const documents = useDocumentStore(
    (state) => state.documentsByChat[chatId] ?? [],
  );
  const documentsLoading = useDocumentStore((state) =>
    Boolean(state.loadingByChat[chatId]),
  );
  const documentsUploading = useDocumentStore((state) =>
    Boolean(state.uploadingByChat[chatId]),
  );
  const documentsError = useDocumentStore(
    (state) => state.errorByChat[chatId] ?? null,
  );
  const selectedDocumentId = useDocumentStore(
    (state) => state.selectedDocumentIdByChat[chatId] ?? null,
  );
  const mutatingDocumentIds = useDocumentStore(
    (state) => state.mutatingDocumentIds,
  );

  const workspaceSelectedDocumentId = useWorkspaceStore(
    (state) => state.selectedDocumentId,
  );

  const setActiveChatId = useWorkspaceStore((state) => state.setActiveChatId);
  const setSelectedDocumentId = useWorkspaceStore(
    (state) => state.setSelectedDocumentId,
  );

  useEffect(() => {
    setActiveChatId(chatId);

    if (activeChatId !== chatId) {
      useChatStore.getState().setActiveChat(chatId);
    }
  }, [activeChatId, chatId, setActiveChatId]);

  useEffect(() => {
    void loadDocuments(chatId).catch(() => {});
  }, [chatId]);

  useEffect(() => {
    if (selectedDocumentId !== workspaceSelectedDocumentId) {
      setSelectedDocumentId(selectedDocumentId);
    }
  }, [selectedDocumentId, setSelectedDocumentId, workspaceSelectedDocumentId]);

  const selectedDocument =
    documents.find((document) => document.id === selectedDocumentId) ?? null;

  const readyDocuments = documents.filter(
    (document) => document.status === "ready",
  );

  async function handleNewChat() {
    if (isCreatingChat) {
      return;
    }

    setIsCreatingChat(true);

    try {
      const newChatId = await chatSessionActions.createChat();

      setMobilePanel(null);
      router.push(`/dashboard/chat/${newChatId}`);
    } finally {
      setIsCreatingChat(false);
    }
  }

  function handleDocumentSelect(document: Document) {
    if (document.status !== "ready") {
      return;
    }

    if (selectedDocumentId !== document.id) {
      const changed = selectDocument(chatId, document.id);

      if (!changed) {
        return;
      }
    }

    setSelectedDocumentId(document.id);
    setMobilePanel(null);
  }

  async function handleDocumentDelete(document: Document) {
    const confirmed = window.confirm(
      `Delete "${document.filename}"? This removes the document from this research workspace.`,
    );

    if (!confirmed) {
      return;
    }

    await deleteDocument(chatId, document.id);

    if (selectedDocumentId === document.id) {
      const replacement = readyDocuments.find(
        (candidate) => candidate.id !== document.id,
      );

      if (replacement) {
        selectDocument(chatId, replacement.id);
        setSelectedDocumentId(replacement.id);
      } else {
        setSelectedDocumentId(null);
      }
    }
  }

  function handleUploadClick() {
    if (isUploading || documentsUploading) {
      return;
    }

    fileInputRef.current?.click();
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    event.target.value = "";

    if (!file) {
      return;
    }

    setIsUploading(true);

    try {
      const response = await uploadDocument(chatId, file);

      await loadDocuments(chatId);

      const uploadedDocumentId = response.document?.id;

      if (uploadedDocumentId) {
        const latestDocument = useDocumentStore
          .getState()
          .documentsByChat[
            chatId
          ]?.find((document) => document.id === uploadedDocumentId);

        if (latestDocument?.status === "ready") {
          selectDocument(chatId, latestDocument.id);
          setSelectedDocumentId(latestDocument.id);
        }
      }
    } catch {
      // Upload errors are stored by document-actions.
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="flex h-dvh min-h-0 overflow-hidden bg-background text-foreground">
      {mobilePanel !== null && (
        <button
          type="button"
          aria-label="Close workspace panel"
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] lg:hidden"
          onClick={() => setMobilePanel(null)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[min(20rem,calc(100vw-2rem))] flex-col",
          "border-r border-border bg-background",
          "transition-transform duration-200 ease-out",
          "lg:relative lg:z-auto lg:translate-x-0",
          mobilePanel === "navigation" ? "translate-x-0" : "-translate-x-full",
          navigationCollapsed ? "lg:w-16" : "lg:w-72",
        )}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-3">
          {!navigationCollapsed && (
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <span className="text-sm font-semibold">H</span>
              </div>

              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  AI Research Copilot
                </p>
                <p className="truncate text-[11px] text-muted-foreground">
                  Research workspace
                </p>
              </div>
            </div>
          )}

          {navigationCollapsed && (
            <div className="mx-auto flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <span className="text-sm font-semibold">H</span>
            </div>
          )}

          <button
            type="button"
            aria-label="Close navigation"
            className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
            onClick={() => setMobilePanel(null)}
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="shrink-0 p-3">
          <button
            type="button"
            disabled={isCreatingChat}
            onClick={() => void handleNewChat()}
            className={cn(
              "flex h-10 w-full items-center rounded-lg",
              "bg-primary text-primary-foreground",
              "text-sm font-medium transition-opacity hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:pointer-events-none disabled:opacity-50",
              navigationCollapsed
                ? "justify-center px-0"
                : "justify-start gap-2 px-3",
            )}
          >
            {isCreatingChat ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <Plus className="size-4" />
            )}

            {!navigationCollapsed && (
              <span>{isCreatingChat ? "Creating..." : "New research"}</span>
            )}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {!navigationCollapsed && (
            <>
              <div className="mb-2 flex items-center gap-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <span>Conversations</span>
              </div>

              <ChatHistoryList onSelectChat={() => setMobilePanel(null)} />

              <div className="my-4 border-t border-border" />

              <div className="mb-2 flex items-center justify-between px-2">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <FileText className="size-3.5" />
                  <span>Documents</span>
                </div>

                <button
                  type="button"
                  disabled={isUploading || documentsUploading}
                  onClick={handleUploadClick}
                  aria-label="Upload PDF"
                  className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
                >
                  {isUploading || documentsUploading ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <Upload className="size-4" />
                  )}
                </button>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(event) => void handleFileChange(event)}
              />

              {documentsLoading ? (
                <div className="space-y-2 px-1">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div
                      key={index}
                      className="h-10 animate-pulse rounded-lg bg-secondary"
                    />
                  ))}
                </div>
              ) : documents.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border px-3 py-5 text-center">
                  <FileText className="mx-auto mb-2 size-5 text-muted-foreground" />
                  <p className="text-xs font-medium">No research documents</p>
                  <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                    Upload a PDF to ground your research conversation.
                  </p>

                  <button
                    type="button"
                    disabled={isUploading || documentsUploading}
                    onClick={handleUploadClick}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-secondary disabled:pointer-events-none disabled:opacity-50"
                  >
                    <Upload className="size-3.5" />
                    Upload PDF
                  </button>
                </div>
              ) : (
                <div className="space-y-1">
                  {documents.map((document) => {
                    const isSelected = selectedDocumentId === document.id;
                    const isMutating = Boolean(
                      mutatingDocumentIds[document.id],
                    );

                    return (
                      <div
                        key={document.id}
                        className={cn(
                          "group flex items-center gap-1 rounded-lg border px-2 py-2",
                          isSelected
                            ? "border-primary/30 bg-primary/5"
                            : "border-transparent hover:bg-secondary",
                        )}
                      >
                        <button
                          type="button"
                          disabled={document.status !== "ready" || isMutating}
                          onClick={() => handleDocumentSelect(document)}
                          className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:pointer-events-none disabled:opacity-60"
                        >
                          <FileText className="size-4 shrink-0 text-muted-foreground" />

                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-medium">
                              {document.filename}
                            </span>

                            <span className="mt-0.5 block text-[10px] text-muted-foreground">
                              {document.status === "processing"
                                ? "Processing..."
                                : document.status === "failed"
                                  ? "Processing failed"
                                  : document.page_count
                                    ? `${document.page_count} pages`
                                    : "Ready"}
                            </span>
                          </span>
                        </button>

                        <button
                          type="button"
                          disabled={isMutating}
                          aria-label={`Delete ${document.filename}`}
                          onClick={() => void handleDocumentDelete(document)}
                          className="rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100 disabled:pointer-events-none disabled:opacity-50"
                        >
                          {isMutating ? (
                            <LoaderCircle className="size-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="size-3.5" />
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              {documentsError && (
                <div className="mt-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
                  {documentsError}
                </div>
              )}
            </>
          )}
        </div>

        <div className="hidden shrink-0 border-t border-border p-2 lg:block">
          <button
            type="button"
            aria-label={
              navigationCollapsed ? "Expand navigation" : "Collapse navigation"
            }
            onClick={() => setNavigationCollapsed((current) => !current)}
            className={cn(
              "flex h-9 w-full items-center rounded-lg text-xs text-muted-foreground",
              "transition-colors hover:bg-secondary hover:text-foreground",
              navigationCollapsed
                ? "justify-center"
                : "justify-start gap-2 px-3",
            )}
          >
            {navigationCollapsed ? (
              <ChevronRight className="size-4" />
            ) : (
              <>
                <ChevronLeft className="size-4" />
                <span>Collapse navigation</span>
              </>
            )}
          </button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-2 sm:px-3">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              aria-label="Open navigation"
              className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
              onClick={() => setMobilePanel("navigation")}
            >
              <Menu className="size-5" />
            </button>

            <div className="hidden lg:block">
              <button
                type="button"
                aria-label="Toggle navigation"
                onClick={() => setNavigationCollapsed((current) => !current)}
                className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <Menu className="size-4" />
              </button>
            </div>

            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">
                Research workspace
              </p>
              <p className="hidden truncate text-xs text-muted-foreground sm:block">
                {selectedDocument?.filename ?? "Select a document to begin"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Open document panel"
              className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
              onClick={() => setMobilePanel("document")}
            >
              <FileText className="size-4" />
            </button>

            <button
              type="button"
              aria-label="Open chat panel"
              className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
              onClick={() => setMobilePanel("chat")}
            >
              <ChevronDown className="size-4" />
            </button>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_minmax(22rem,32rem)]">
          <section
            aria-label="Document viewer"
            className={cn(
              "relative min-h-0 min-w-0 overflow-hidden border-b border-border bg-muted/20",
              "lg:border-b-0 lg:border-r",
              mobilePanel === "document"
                ? "fixed inset-0 z-50 flex"
                : "hidden lg:flex",
              "flex-col",
            )}
          >
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-3">
              <div className="flex min-w-0 items-center gap-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" />

                <span className="truncate text-xs font-medium">
                  {selectedDocument?.filename ?? "Document viewer"}
                </span>
              </div>

              <button
                type="button"
                aria-label="Close document panel"
                className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
                onClick={() => setMobilePanel(null)}
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-4 sm:p-6">
              {selectedDocument ? (
                <div className="w-full max-w-xl rounded-xl border border-border bg-background p-6 text-center shadow-sm">
                  <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-secondary">
                    <FileText className="size-6 text-muted-foreground" />
                  </div>

                  <h2 className="mt-4 truncate text-sm font-semibold">
                    {selectedDocument.filename}
                  </h2>

                  <p className="mt-1 text-xs text-muted-foreground">
                    {selectedDocument.page_count
                      ? `${selectedDocument.page_count} pages`
                      : "PDF document"}
                  </p>

                  <div className="mt-5 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-5">
                    <p className="text-sm font-medium">PDF viewer ready</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      The selected document is connected to this workspace. The
                      interactive PDF renderer and page navigation are added in
                      the next P0 step.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="max-w-sm px-6 text-center">
                  <div className="mx-auto flex size-14 items-center justify-center rounded-2xl border border-border bg-background">
                    <FileText className="size-7 text-muted-foreground" />
                  </div>

                  <h2 className="mt-4 text-sm font-semibold">
                    No document selected
                  </h2>

                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Upload a PDF or select a processed document from the
                    workspace sidebar to start document-grounded research.
                  </p>

                  <button
                    type="button"
                    disabled={isUploading || documentsUploading}
                    onClick={handleUploadClick}
                    className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:pointer-events-none disabled:opacity-50"
                  >
                    {isUploading || documentsUploading ? (
                      <LoaderCircle className="size-3.5 animate-spin" />
                    ) : (
                      <Upload className="size-3.5" />
                    )}
                    Upload PDF
                  </button>
                </div>
              )}
            </div>
          </section>

          <section
            aria-label="AI chat"
            className={cn(
              "min-h-0 min-w-0 overflow-hidden bg-background",
              mobilePanel === "chat"
                ? "fixed inset-0 z-50 flex"
                : "hidden lg:flex",
              "flex-col",
            )}
          >
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
              <div className="flex min-w-0 items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <span className="text-xs font-semibold">AI</span>
                </div>

                <div className="min-w-0">
                  <p className="text-xs font-semibold">Research Copilot</p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {selectedDocument
                      ? `Grounded in ${selectedDocument.filename}`
                      : "General conversation"}
                  </p>
                </div>
              </div>

              <button
                type="button"
                aria-label="Close chat panel"
                className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground lg:hidden"
                onClick={() => setMobilePanel(null)}
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1">
              <ChatArea />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
