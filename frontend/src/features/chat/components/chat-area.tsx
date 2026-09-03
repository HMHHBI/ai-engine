"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { useState } from "react";

import { useChatStore } from "@/features/chat/store/chat-store";
import { MessageList } from "@/features/chat/components/message-list";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { MessageSkeleton } from "@/features/chat/components/message-skeleton";
import { EmptyState } from "@/components/feedback/empty-state";
import { chatActions } from "@/features/chat/actions/chat-actions";
import type { ChatMessage } from "@/types/api";

const EMPTY_MESSAGES: ChatMessage[] = [];

export function ChatArea() {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const messages = useChatStore((state) =>
    activeChatId === null
      ? EMPTY_MESSAGES
      : state.messagesByChat[activeChatId] ?? EMPTY_MESSAGES,
  );

  const isChatLoading = useChatStore((state) =>
    activeChatId === null ? false : Boolean(state.loadingChatIds[activeChatId]),
  );

  const streamingStatus = useChatStore((state) =>
    activeChatId === null
      ? "idle"
      : state.streamingStatusByChat[activeChatId] ?? "idle",
  );

  const [retrying, setRetrying] = useState(false);

  async function handleRetryLastMessage() {
    if (activeChatId === null || retrying) return;

    const lastUserMessage = [...messages]
      .reverse()
      .find((msg) => msg.role === "user");

    if (!lastUserMessage) return;

    setRetrying(true);
    try {
      await chatActions.sendMessage({
        chatId: activeChatId,
        prompt: lastUserMessage.content,
      });
    } catch {
      // Handled in stream service
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-background">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {isChatLoading ? (
          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            <MessageSkeleton />
          </div>
        ) : messages.length === 0 ? (
          <EmptyState
            title="Start a conversation"
            description="Type a message below or attach files to begin chatting with the AI."
          />
        ) : (
          <MessageList chatId={activeChatId} />
        )}
      </div>

      {streamingStatus === "error" && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-between border-t border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0" />
            <span>Response incomplete due to an error.</span>
          </div>

          <button
            type="button"
            disabled={retrying}
            onClick={() => void handleRetryLastMessage()}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 font-medium hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <RefreshCw
              className={retrying ? "size-3 animate-spin" : "size-3"}
            />
            <span>{retrying ? "Retrying..." : "Retry"}</span>
          </button>
        </div>
      )}

      <ChatComposer chatId={activeChatId} />
    </div>
  );
}
