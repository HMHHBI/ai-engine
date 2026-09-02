"use client";

import { useEffect, useRef } from "react";

import { MessageBubble } from "@/features/chat/components/message-bubble";
import { useChatStore } from "@/features/chat/store/chat-store";
import type { ChatMessage } from "@/types/api";

const EMPTY_MESSAGES: ChatMessage[] = [];

interface MessageListProps {
  chatId: number | null;
}

export function MessageList({ chatId }: MessageListProps) {
  const messages = useChatStore((state) =>
    chatId === null
      ? EMPTY_MESSAGES
      : (state.messagesByChat[chatId] ?? EMPTY_MESSAGES),
  );

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages.length]);

  if (chatId === null) {
    return null;
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="pb-6 pt-4">
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id ?? `${message.role}-${index}`}
            message={message}
          />
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
