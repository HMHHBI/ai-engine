"use client";

import { CheckCircle2, LoaderCircle } from "lucide-react";

import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { cn } from "@/lib/utils";

interface RagStatusBadgeProps {
  chatId: number | null;
  className?: string;
}

export function RagStatusBadge({ chatId, className }: RagStatusBadgeProps) {
  const session = useChatSessionStore((state) =>
    chatId === null ? null : state.sessions.find((item) => item.id === chatId),
  );

  const pdfState = useChatStore((state) =>
    chatId === null ? null : state.pdfStateByChat[chatId],
  );

  if (chatId === null) {
    return null;
  }

  const isProcessing =
    pdfState?.status === "uploading" || pdfState?.status === "processing";
  const isReady = pdfState?.status === "ready" || session?.has_pdf === true;

  if (!isProcessing && !isReady) {
    return null;
  }

  if (isProcessing) {
    return (
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 px-2.5 py-1 text-xs text-muted-foreground",
          className,
        )}
      >
        <LoaderCircle className="size-3 animate-spin text-foreground" />
        <span>Indexing PDF…</span>
      </div>
    );
  }

  const filename = pdfState?.filename;
  const chunkText =
    pdfState?.chunksCount !== null && pdfState?.chunksCount !== undefined
      ? ` · ${pdfState.chunksCount} chunks`
      : "";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary",
        className,
      )}
      title={filename ? `RAG active for ${filename}` : "PDF context loaded"}
    >
      <CheckCircle2 className="size-3" />
      <span className="max-w-40 truncate">
        {filename ? `${filename}${chunkText}` : "RAG Ready"}
      </span>
    </div>
  );
}
