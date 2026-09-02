"use client";

import { Menu, PanelLeft } from "lucide-react";

import { IconButton } from "@/components/ui/icon-button";
import { RagStatusBadge } from "@/features/chat/components/rag-status-badge";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";

interface AppHeaderProps {
  onOpenMobileSidebar: () => void;
  onToggleSidebar: () => void;
}

export function AppHeader({
  onOpenMobileSidebar,
  onToggleSidebar,
}: AppHeaderProps) {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const activeSession = useChatSessionStore((state) =>
    activeChatId === null
      ? null
      : state.sessions.find((item) => item.id === activeChatId),
  );

  const title = activeSession?.title ?? "AI Engine";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-3">
      <div className="flex min-w-0 items-center gap-2">
        <div className="md:hidden">
          <IconButton label="Open sidebar" onClick={onOpenMobileSidebar}>
            <Menu className="size-5" />
          </IconButton>
        </div>

        <div className="hidden md:block">
          <IconButton label="Toggle sidebar" onClick={onToggleSidebar}>
            <PanelLeft className="size-4" />
          </IconButton>
        </div>

        <div className="min-w-0">
          <h1 className="truncate text-sm font-medium">{title}</h1>
        </div>
      </div>

      <div className="ml-2 flex shrink-0 items-center">
        <RagStatusBadge chatId={activeChatId} />
      </div>
    </header>
  );
}
