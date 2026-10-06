"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  Edit2,
  FileText,
  MessageSquare,
  MoreHorizontal,
  Trash2,
  X,
} from "lucide-react";
import type { ChatSession } from "@/types/api";
import { cn } from "@/lib/utils";

interface ChatHistoryItemProps {
  session: ChatSession;
  isActive: boolean;
  isMutating: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => Promise<void>;
  onDeleteRequest: () => void;
}

const PERSONA_LABELS: Record<string, string> = {
  academic: "Academic",
  legal: "Legal",
  developer: "Developer",
  simple: "Simple",
  default: "General",
};

function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) {
    return "No activity";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "No activity";
  }

  const now = Date.now();
  const difference = Math.max(0, now - date.getTime());

  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (difference < minute) {
    return "Just now";
  }

  if (difference < hour) {
    return `${Math.floor(difference / minute)}m ago`;
  }

  if (difference < day) {
    return `${Math.floor(difference / hour)}h ago`;
  }

  if (difference < 2 * day) {
    return "Yesterday";
  }

  if (difference < 7 * day) {
    return `${Math.floor(difference / day)}d ago`;
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function getMaterialLabel(session: ChatSession): string {
  if (
    session.attached_documents_count === 1 &&
    session.primary_document_title
  ) {
    return session.primary_document_title;
  }

  if (session.attached_documents_count > 1) {
    return `${session.attached_documents_count} docs`;
  }

  return "Research session";
}

export function ChatHistoryItem({
  session,
  isActive,
  isMutating,
  onSelect,
  onRename,
  onDeleteRequest,
}: ChatHistoryItemProps) {
  const [isEditing, setIsEditing] = useState(false);

  const [draftTitle, setDraftTitle] = useState(session.title);

  const [menuOpen, setMenuOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraftTitle(session.title);
  }, [session.title]);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }

    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);

      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [menuOpen]);

  async function handleSave() {
    const trimmed = draftTitle.trim();

    if (!trimmed || trimmed === session.title) {
      setIsEditing(false);
      setDraftTitle(session.title);
      return;
    }

    try {
      await onRename(trimmed);
      setIsEditing(false);
    } catch {
      setDraftTitle(session.title);
      setIsEditing(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void handleSave();
    } else if (event.key === "Escape") {
      setIsEditing(false);
      setDraftTitle(session.title);
    }
  }

  const personaLabel =
    PERSONA_LABELS[session.persona ?? "default"] ?? "General";

  const materialLabel = getMaterialLabel(session);

  const relativeTime = formatRelativeTime(session.last_active_at);

  const title =
    session.title || session.primary_document_title || "New Research";

  if (isEditing) {
    return (
      <div className="flex w-full items-center gap-1 rounded-xl bg-secondary p-2">
        <input
          ref={inputRef}
          type="text"
          value={draftTitle}
          disabled={isMutating}
          onChange={(event) => setDraftTitle(event.target.value)}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1 bg-transparent px-1 text-xs text-foreground focus:outline-none"
        />

        <button
          type="button"
          disabled={isMutating}
          onClick={() => void handleSave()}
          aria-label="Save title"
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
        >
          <Check className="size-3.5" />
        </button>

        <button
          type="button"
          disabled={isMutating}
          onClick={() => {
            setIsEditing(false);
            setDraftTitle(session.title);
          }}
          aria-label="Cancel rename"
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid={`research-session-${session.id}`}
      className={cn(
        "group relative w-full rounded-xl border transition-colors",
        isActive
          ? "border-primary/20 bg-primary/5"
          : "border-transparent hover:border-border hover:bg-secondary/50",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="w-full min-w-0 px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
      >
        <div className="flex min-w-0 items-start gap-2.5">
          <div
            className={cn(
              "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg",
              isActive
                ? "bg-primary/10 text-primary"
                : "bg-secondary text-muted-foreground",
            )}
          >
            <MessageSquare className="size-3.5" aria-hidden="true" />
          </div>

          <div className="min-w-0 flex-1">
            <p
              className="truncate text-xs font-semibold text-foreground"
              title={title}
            >
              {title}
            </p>

            <div className="mt-1.5 flex min-w-0 items-center gap-1.5">
              <FileText
                className="size-3 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />

              <span
                className="min-w-0 truncate text-[10px] text-muted-foreground"
                title={materialLabel}
              >
                {materialLabel}
              </span>

              <span
                aria-hidden="true"
                className="text-[10px] text-muted-foreground/60"
              >
                ·
              </span>

              <span className="shrink-0 rounded-md bg-secondary px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                {personaLabel}
              </span>
            </div>

            <p className="mt-1.5 text-[10px] text-muted-foreground">
              Active {relativeTime}
            </p>
          </div>
        </div>
      </button>

      <div ref={menuRef} className="absolute right-1.5 top-1.5">
        <button
          type="button"
          disabled={isMutating}
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((previous) => !previous);
          }}
          aria-label="Chat options"
          className={cn(
            "flex size-7 items-center justify-center rounded-md hover:bg-background/80 hover:text-foreground",
            menuOpen
              ? "opacity-100"
              : "opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100",
            isMutating && "cursor-not-allowed opacity-40",
          )}
        >
          <MoreHorizontal className="size-4" />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-full z-50 mt-1 w-32 rounded-lg border border-border bg-background p-1 shadow-md">
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                setIsEditing(true);
              }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-foreground hover:bg-secondary"
            >
              <Edit2 className="size-3.5" />
              <span>Rename</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onDeleteRequest();
              }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="size-3.5" />
              <span>Delete</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
