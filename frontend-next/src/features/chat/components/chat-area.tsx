"use client";

import { useChatStore } from "@/features/chat/store/chat-store";

import { ChatComposer } from "@/features/chat/components/chat-composer";
import { ChatEmptyState } from "@/features/chat/components/chat-empty-state";
import { MessageList } from "@/features/chat/components/message-list";
import { StreamingIndicator } from "@/features/chat/components/streaming-indicator";

export function ChatArea() {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const hasMessages = useChatStore(
    (state) =>
      activeChatId !== null &&
      (state.messagesByChat[activeChatId]?.length ?? 0) > 0,
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

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {isChatLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <div className="size-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
            <span>Loading conversation...</span>
          </div>
        </div>
      ) : activeChatId === null || !hasMessages ? (
        <ChatEmptyState />
      ) : (
        <MessageList chatId={activeChatId} />
      )}

      {streamingStatus === "streaming" && <StreamingIndicator />}

      <ChatComposer chatId={activeChatId} />
    </section>
  );
}
