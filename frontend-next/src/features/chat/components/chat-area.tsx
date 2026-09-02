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

  const streamingStatus = useChatStore((state) =>
    activeChatId === null
      ? "idle"
      : (state.streamingStatusByChat[activeChatId] ?? "idle"),
  );

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {activeChatId === null || !hasMessages ? (
        <ChatEmptyState />
      ) : (
        <MessageList chatId={activeChatId} />
      )}

      {streamingStatus === "streaming" && <StreamingIndicator />}

      <ChatComposer chatId={activeChatId} />
    </section>
  );
}
