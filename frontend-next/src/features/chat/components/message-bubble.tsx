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
      <div className="mx-auto w-full max-w-3xl px-3 py-2 sm:px-4">
        <div
          className={cn(
            "rounded-lg border border-border",
            "bg-secondary/50 px-3 py-2.5 sm:px-4 sm:py-3",
            "text-xs text-muted-foreground sm:text-sm",
          )}
        >
          <div className="min-w-0 wrap-anywhere whitespace-pre-wrap">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group mx-auto flex w-full max-w-3xl gap-2 px-2.5 py-3 sm:gap-3 sm:px-4 sm:py-4",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div
          className={cn(
            "mt-0.5 flex size-6 shrink-0 items-center justify-center sm:size-7",
            "rounded-full border border-border bg-card",
          )}
          aria-hidden="true"
        >
          <Bot className="size-3.5 text-muted-foreground sm:size-4" />
        </div>
      )}

      <div
        className={cn(
          "flex min-w-0 max-w-[calc(100%-2rem)] flex-col gap-1 sm:max-w-[85%]",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-xs leading-5 sm:px-4 sm:py-3 sm:text-sm sm:leading-6",
            isUser
              ? "bg-primary text-primary-foreground"
              : "border border-border bg-card text-foreground",
          )}
        >
          <div className="min-w-0 wrap-anywhere whitespace-pre-wrap">
            {message.content}
            {!isUser && isStreaming && (
              <span
                className="ml-1 inline-block h-3.5 w-1 animate-pulse rounded-sm bg-current align-[-2px] sm:h-4"
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
          className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary sm:size-7"
          aria-hidden="true"
        >
          <User className="size-3.5 text-muted-foreground sm:size-4" />
        </div>
      )}
    </div>
  );
}
