"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquareDashed } from "lucide-react";

import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { ChatHistoryItem } from "@/features/chat/components/chat-history-item";
import { ChatDeleteDialog } from "@/features/chat/components/chat-delete-dialog";
import { Skeleton } from "@/components/feedback/skeleton";
import { ErrorState } from "@/components/feedback/error-state";
import { EmptyState } from "@/components/feedback/empty-state";

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

  const [retrying, setRetrying] = useState(false);

  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void chatSessionActions.loadChats().catch(() => {});
  }, []);

  const targetSession = sessions.find(
    (session) => session.id === deleteTargetId,
  );

  async function handleRetry() {
    setRetrying(true);

    try {
      await chatSessionActions.loadChats();
    } finally {
      setRetrying(false);
    }
  }

  async function handleCreateChat() {
    setCreating(true);

    try {
      const newId = await chatSessionActions.createChat();

      onSelectChat?.();

      router.push(`/dashboard/chat/${newId}`);
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteConfirm() {
    if (deleteTargetId === null) {
      return;
    }

    try {
      const wasActive = await chatSessionActions.deleteChat(deleteTargetId);

      setDeleteTargetId(null);

      if (wasActive) {
        router.replace("/dashboard");
      }
    } catch {
      setDeleteTargetId(null);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2 py-1">
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={`skeleton-${index}`}
            className="rounded-xl px-3 py-2.5"
          >
            <div className="space-y-2">
              <Skeleton
                className={`h-3 rounded ${index % 2 === 0 ? "w-3/4" : "w-2/3"}`}
              />
              <Skeleton
                className={`h-2.5 rounded ${index % 3 === 0 ? "w-1/2" : "w-2/5"}`}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load research sessions"
        message={error}
        actionLabel="Retry"
        retrying={retrying}
        onAction={() => void handleRetry()}
        className="px-1 py-4"
      />
    );
  }

  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={<MessageSquareDashed className="size-4" />}
        title="No research sessions yet"
        description="Start a new research session with AI Engine."
        actionLabel="New research"
        actionLoading={creating}
        onAction={() => void handleCreateChat()}
        className="px-1 py-6"
      />
    );
  }

  return (
    <>
      <div className="space-y-1.5">
        {sessions.map((session, index) => {
          const isActive = pathname === `/dashboard/chat/${session.id}`;

          const isMutating = Boolean(mutatingChatIds[session.id]);

          const itemKey = session.id
            ? `session-${session.id}`
            : `session-idx-${index}`;

          return (
            <ChatHistoryItem
              key={itemKey}
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
          chatTitle={targetSession?.title ?? "this research session"}
          isDeleting={Boolean(mutatingChatIds[deleteTargetId])}
          onConfirm={() => void handleDeleteConfirm()}
          onCancel={() => setDeleteTargetId(null)}
        />
      )}
    </>
  );
}
