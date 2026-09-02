"use client";

import { useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

import { useChatStore } from "@/features/chat/store/chat-store";
import { chatActions } from "@/features/chat/actions/chat-actions";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatEmptyState } from "@/features/chat/components/chat-empty-state";
import { MessageList } from "@/features/chat/components/message-list";
import { StreamingIndicator } from "@/features/chat/components/streaming-indicator";
import { MessageSkeleton } from "@/features/chat/components/message-skeleton";

export function ChatArea() {
  const activeChatId = useChatStore((state) => state.activeChatId);
  const [retrying, setRetrying] = useState(false);

  const messages = useChatStore((state) =>
    activeChatId !== null ? (state.messagesByChat[activeChatId] ?? []) : [],
  );

  const isChatLoading = useChatStore(
    (state) =>
      activeChatId !== null && Boolean(state.loadingChatIds[activeChatId]),
  );

  const streamingStatus = useChatStore((state) =>
    activeChatId === null
      ? "idle"
      : (state.streamingStatusByChat[activeChatId] ?? "idle"),
  );

  const hasMessages = messages.length > 0;

  async function handleRetryLastMessage() {
    if (activeChatId === null || retrying) return;

    // Find the last user message to resend
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.role === "user");
    if (!lastUserMessage) return;

    setRetrying(true);
    try {
      await chatActions.sendMessage({
        chatId: activeChatId,
        prompt: lastUserMessage.content,
      });
    } catch {
      // Handled in store
    } finally {
      setRetrying(false);
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {isChatLoading ? (
        <div className="flex flex-1 items-start justify-center overflow-y-auto">
          <MessageSkeleton />
        </div>
      ) : activeChatId === null || !hasMessages ? (
        <ChatEmptyState />
      ) : (
        <MessageList chatId={activeChatId} />
      )}

      {streamingStatus === "streaming" && <StreamingIndicator />}

      {streamingStatus === "error" && (
        <div className="border-t border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <AlertCircle className="size-4 shrink-0" />
              <span>Response could not be completed.</span>
            </div>

            <button
              type="button"
              disabled={retrying}
              onClick={() => void handleRetryLastMessage()}
              className="inline-flex items-center gap-1 font-medium underline underline-offset-2 hover:opacity-80 disabled:opacity-50"
            >
              <RefreshCw
                className={retrying ? "size-3 animate-spin" : "size-3"}
              />
              <span>{retrying ? "Retrying..." : "Retry"}</span>
            </button>
          </div>
        </div>
      )}

      <ChatComposer chatId={activeChatId} />
    </section>
  );
}
