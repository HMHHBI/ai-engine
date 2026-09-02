"use client";

import { Bot, User } from "lucide-react";

import { CopyButton } from "@/features/chat/components/copy-button";
import type { ChatMessage } from "@/types/api";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function MessageBubble({
  message,
  isStreaming = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-2">
        <div
          className={cn(
            "rounded-lg border border-border",
            "bg-secondary/50 px-4 py-3",
            "text-sm text-muted-foreground",
          )}
        >
          <div className="whitespace-pre-wrap break-word">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group mx-auto flex w-full max-w-3xl gap-3 px-3 py-4 sm:px-4",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div
          className={cn(
            "mt-0.5 flex size-7 shrink-0 items-center justify-center",
            "rounded-full border border-border bg-card",
          )}
          aria-hidden="true"
        >
          <Bot className="size-4 text-muted-foreground" />
        </div>
      )}

      <div
        className={cn(
          "flex max-w-[calc(100%-2.5rem)] flex-col gap-1 sm:max-w-[85%]",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-6",
            isUser
              ? "bg-primary text-primary-foreground"
              : "border border-border bg-card text-foreground",
          )}
        >
          <div className="whitespace-pre-wrap break-word">
            {message.content}
            {!isUser && isStreaming && (
              <span
                className="ml-1 inline-block h-4 w-1 animate-pulse rounded-sm bg-current align-[-2px]"
                aria-label="Generating"
              />
            )}
          </div>
        </div>

        <CopyButton
          value={message.content}
          className={cn(
            "opacity-0 transition-opacity group-hover:opacity-100",
            "focus-visible:opacity-100 max-sm:opacity-100",
          )}
        />
      </div>

      {isUser && (
        <div
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary"
          aria-hidden="true"
        >
          <User className="size-4 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
