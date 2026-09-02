import { Bot, User } from "lucide-react";

import type { ChatMessage } from "@/types/api";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-2">
        <div className="rounded-lg border border-border bg-secondary/50 px-4 py-3 text-sm text-muted-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-3xl gap-3 px-4 py-4",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-card">
          <Bot className="size-4 text-muted-foreground" />
        </div>
      )}

      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-card text-foreground",
        )}
      >
        <div className="whitespace-pre-wrap break-word">{message.content}</div>
      </div>

      {isUser && (
        <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary">
          <User className="size-4 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
