"use client";

import { ArrowUp, Square } from "lucide-react";
import { useState } from "react";

import { chatActions } from "@/features/chat/actions/chat-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  chatId: number | null;
}

export function ChatComposer({ chatId }: ChatComposerProps) {
  const [prompt, setPrompt] = useState("");

  const status = useChatStore((state) =>
    chatId === null ? "idle" : (state.streamingStatusByChat[chatId] ?? "idle"),
  );

  const isStreaming = status === "streaming";
  const canSend = chatId !== null && prompt.trim().length > 0 && !isStreaming;

  async function handleSubmit() {
    if (!canSend || chatId === null) {
      return;
    }

    const value = prompt.trim();
    setPrompt("");

    try {
      await chatActions.sendMessage({
        chatId,
        prompt: value,
      });
    } catch {
      // Handled via store state updates
    }
  }

  function handleStop() {
    chatActions.stopStreaming();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background">
      <div className="mx-auto w-full max-w-3xl px-4 py-4">
        <div
          className={cn(
            "relative rounded-2xl border border-border bg-card",
            "shadow-sm transition-colors",
            "focus-within:border-ring",
          )}
        >
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={chatId === null || isStreaming}
            placeholder={
              chatId === null ? "Start a new chat" : "Message AI Engine…"
            }
            rows={1}
            className={cn(
              "block min-h-14 w-full resize-none",
              "bg-transparent px-4 pb-12 pt-4",
              "text-sm leading-6 text-foreground",
              "outline-none placeholder:text-muted-foreground",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />

          <div className="absolute bottom-2 right-2">
            {isStreaming ? (
              <button
                type="button"
                onClick={handleStop}
                aria-label="Stop generating"
                title="Stop generating"
                className={cn(
                  "flex size-9 items-center justify-center",
                  "rounded-xl bg-secondary",
                  "text-foreground",
                  "transition-colors hover:bg-muted",
                  "focus-visible:outline-none",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                <Square className="size-4 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={!canSend}
                aria-label="Send message"
                title="Send message"
                className={cn(
                  "flex size-9 items-center justify-center",
                  "rounded-xl bg-primary text-primary-foreground",
                  "transition-opacity hover:opacity-90",
                  "focus-visible:outline-none",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                  "disabled:pointer-events-none disabled:opacity-40",
                )}
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>
        </div>

        <p className="mt-2 text-center text-xs text-muted-foreground">
          Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  );
}
