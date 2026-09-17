"use client";

import { useEffect } from "react";

import { ChatArea } from "@/features/chat/components/chat-area";
import { loadDocuments } from "@/features/documents/document-actions";
import { useDocumentStore } from "@/features/documents/document-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useWorkspaceStore } from "@/features/workspace/store/workspace-store";
import { PdfViewer } from "@/features/workspace/components/PdfViewer";

interface ResearchWorkspaceProps {
  chatId: number;
}

export function ResearchWorkspace({ chatId }: ResearchWorkspaceProps) {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const documents = useDocumentStore(
    (state) => state.documentsByChat[chatId] ?? [],
  );
  const selectedDocumentId = useDocumentStore(
    (state) => state.selectedDocumentIdByChat[chatId] ?? null,
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

  return (
    <div className="grid h-full min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_minmax(22rem,32rem)]">
      <section
        aria-label="Document viewer"
        className="relative hidden min-h-0 min-w-0 flex-col overflow-hidden border-r border-border bg-muted/20 lg:flex"
      >
        <PdfViewer document={selectedDocument} className="min-h-0 flex-1" />
      </section>

      <section
        aria-label="AI chat"
        className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
      >
        <div className="min-h-0 flex-1">
          <ChatArea />
        </div>
      </section>
    </div>
  );
}
