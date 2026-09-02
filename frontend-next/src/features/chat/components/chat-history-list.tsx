"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { ChatHistoryItem } from "@/features/chat/components/chat-history-item";
import { ChatDeleteDialog } from "@/features/chat/components/chat-delete-dialog";

interface ChatHistoryListProps {
  onSelectChat?: () => void;
}

export function ChatHistoryList({ onSelectChat }: ChatHistoryListProps) {
  const router = useRouter();
  const pathname = usePathname();

  const sessions = useChatSessionStore((state) => state.sessions);
  const isLoading = useChatSessionStore((state) => state.isLoading);
  const error = useChatSessionStore((state) => state.error);
  const mutatingChatIds = useChatSessionStore((state) => state.mutatingChatIds);

  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);

  useEffect(() => {
    void chatSessionActions.loadChats().catch(() => {});
  }, []);

  const targetSession = sessions.find((s) => s.id === deleteTargetId);

  async function handleDeleteConfirm() {
    if (deleteTargetId === null) return;

    try {
      const wasActive = await chatSessionActions.deleteChat(deleteTargetId);
      setDeleteTargetId(null);
      if (wasActive) {
        router.replace("/dashboard");
      }
    } catch {
      // Keep state intact on failure
      setDeleteTargetId(null);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-1">
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={index}
            className="h-10 animate-pulse rounded-lg bg-secondary"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-2 py-3 text-xs text-muted-foreground">
        <p>Unable to load chats.</p>
        <button
          type="button"
          onClick={() => {
            void chatSessionActions.loadChats().catch(() => {});
          }}
          className="mt-1 text-foreground underline underline-offset-2"
        >
          Retry
        </button>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="px-2 py-3 text-xs text-muted-foreground">
        No conversations yet.
      </div>
    );
  }

  return (
    <>
      <div className="space-y-1">
        {sessions.map((session) => {
          const isActive = pathname === `/dashboard/chat/${session.id}`;
          const isMutating = Boolean(mutatingChatIds[session.id]);

          return (
            <ChatHistoryItem
              key={session.id}
              session={session}
              isActive={isActive}
              isMutating={isMutating}
              onSelect={() => {
                onSelectChat?.();
                router.push(`/dashboard/chat/${session.id}`);
              }}
              onRename={async (newTitle) => {
                await chatSessionActions.renameChat(session.id, newTitle);
              }}
              onDeleteRequest={() => setDeleteTargetId(session.id)}
            />
          );
        })}
      </div>

      {deleteTargetId !== null && (
        <ChatDeleteDialog
          chatTitle={targetSession?.title ?? "this chat"}
          isDeleting={Boolean(mutatingChatIds[deleteTargetId])}
          onConfirm={() => void handleDeleteConfirm()}
          onCancel={() => setDeleteTargetId(null)}
        />
      )}
    </>
  );
}
