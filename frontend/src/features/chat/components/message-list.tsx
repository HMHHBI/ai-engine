"use client";

import { ArrowDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { MessageBubble } from "@/features/chat/components/message-bubble";
import { useChatStore } from "@/features/chat/store/chat-store";
import type { ChatMessage } from "@/types/api";
import { cn } from "@/lib/utils";

const EMPTY_MESSAGES: ChatMessage[] = [];
const BOTTOM_THRESHOLD = 96;

interface MessageListProps {
  chatId: number | null;
}

export function MessageList({ chatId }: MessageListProps) {
  const messages = useChatStore((state) =>
    chatId === null
      ? EMPTY_MESSAGES
      : (state.messagesByChat[chatId] ?? EMPTY_MESSAGES),
  );

  const streamingStatus = useChatStore((state) =>
    chatId === null ? "idle" : (state.streamingStatusByChat[chatId] ?? "idle"),
  );

  const isStreaming = streamingStatus === "streaming";

  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const [isLocked, setIsLocked] = useState(false);

  const isNearBottom = useCallback(() => {
    const container = containerRef.current;

    if (!container) {
      return true;
    }

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;

    return distanceFromBottom <= BOTTOM_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({
      behavior,
      block: "end",
    });

    setIsLocked(false);
  }, []);

  const handleScroll = useCallback(() => {
    setIsLocked(!isNearBottom());
  }, [isNearBottom]);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    container.addEventListener("scroll", handleScroll, {
      passive: true,
    });

    return () => {
      container.removeEventListener("scroll", handleScroll);
    };
  }, [handleScroll]);

  useEffect(() => {
    if (messages.length === 0) {
      return;
    }

    if (!isLocked) {
      bottomRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    }
  }, [messages.length, isLocked]);

  const lastMessageContent =
    messages.length > 0 ? messages[messages.length - 1]?.content : "";

  useEffect(() => {
    if (!lastMessageContent || isLocked) {
      return;
    }

    bottomRef.current?.scrollIntoView({
      behavior: "auto",
      block: "end",
    });
  }, [lastMessageContent, isLocked]);

  if (chatId === null) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="pb-6 pt-4">
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id ?? `${message.role}-${index}`}
            message={message}
            isStreaming={isStreaming && index === messages.length - 1}
          />
        ))}

        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {isLocked && (
        <button
          type="button"
          onClick={() => scrollToBottom("smooth")}
          className={cn(
            "sticky bottom-4 left-1/2 z-10 -translate-x-1/2",
            "flex items-center gap-2 rounded-full border border-border",
            "bg-card px-3 py-2 text-xs font-medium text-foreground",
            "shadow-md transition-colors hover:bg-secondary",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
          aria-label="Jump to latest message"
        >
          <ArrowDown className="size-3.5" />
          <span>Jump to latest</span>
        </button>
      )}
    </div>
  );
}
