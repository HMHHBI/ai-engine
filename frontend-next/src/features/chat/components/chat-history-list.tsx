"use client";

import { useEffect } from "react";
import { MessageSquare } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { cn } from "@/lib/utils";

interface ChatHistoryListProps {
  onSelectChat?: () => void;
}

export function ChatHistoryList({ onSelectChat }: ChatHistoryListProps) {
  const router = useRouter();
  const pathname = usePathname();

  const sessions = useChatSessionStore((state) => state.sessions);

  const isLoading = useChatSessionStore((state) => state.isLoading);

  const error = useChatSessionStore((state) => state.error);

  useEffect(() => {
    void chatSessionActions.loadChats().catch(() => {
      // Error is tracked in the session store
    });
  }, []);

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
    <div className="space-y-1">
      {sessions.map((session) => {
        const isActive = pathname === `/dashboard/chat/${session.id}`;

        return (
          <button
            key={session.id}
            type="button"
            onClick={() => {
              onSelectChat?.();
              router.push(`/dashboard/chat/${session.id}`);
            }}
            className={cn(
              "flex h-10 w-full items-center gap-3 rounded-lg px-3",
              "text-left text-sm transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isActive
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            <MessageSquare className="size-4 shrink-0" />

            <span className="min-w-0 flex-1 truncate">
              {session.title || "Untitled chat"}
            </span>
          </button>
        );
      })}
    </div>
  );
}
