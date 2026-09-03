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
  const content = message.content || message.text || "";

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
          <div className="min-w-0 break-words whitespace-pre-wrap">
            {content}
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
            "mt-0.5 flex size-7 shrink-0 items-center justify-center",
            "rounded-full border border-border bg-card text-foreground",
          )}
          aria-hidden="true"
        >
          <Bot className="size-4 text-muted-foreground" />
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
            "rounded-2xl px-4 py-2.5 text-xs leading-5 sm:px-4 sm:py-3 sm:text-sm sm:leading-6 shadow-sm",
            isUser
              ? "bg-zinc-100 text-zinc-950 font-medium"
              : "border border-zinc-800 bg-zinc-900 text-zinc-100",
          )}
        >
          <div className="min-w-0 break-words whitespace-pre-wrap">
            {content}
            {!isUser && isStreaming && (
              <span
                className="ml-1 inline-block h-3.5 w-1 animate-pulse rounded-sm bg-current align-[-2px] sm:h-4"
                aria-hidden="true"
              />
            )}
          </div>
        </div>

        {content && (
          <CopyButton
            value={content}
            className={cn(
              "opacity-0 transition-opacity group-hover:opacity-100",
              "focus-visible:opacity-100 max-sm:opacity-100",
            )}
          />
        )}
      </div>

      {isUser && (
        <div
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-300"
          aria-hidden="true"
        >
          <User className="size-4" />
        </div>
      )}
    </div>
  );
}
