"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  Edit2,
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
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
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

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleSave();
    } else if (e.key === "Escape") {
      setIsEditing(false);
      setDraftTitle(session.title);
    }
  }

  if (isEditing) {
    return (
      <div className="flex h-10 w-full items-center gap-1 rounded-lg bg-secondary px-2">
        <input
          ref={inputRef}
          type="text"
          value={draftTitle}
          disabled={isMutating}
          onChange={(e) => setDraftTitle(e.target.value)}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground focus:outline-none"
        />
        <button
          type="button"
          disabled={isMutating}
          onClick={() => void handleSave()}
          aria-label="Save title"
          className="flex size-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-foreground"
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
          className="flex size-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group relative flex h-10 w-full items-center rounded-lg transition-colors",
        isActive
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex h-full min-w-0 flex-1 items-center gap-3 pl-3 pr-2 text-left text-sm focus-visible:outline-none"
      >
        <MessageSquare className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">
          {session.title || "Untitled chat"}
        </span>
      </button>

      {/* Kebab menu toggle */}
      <div ref={menuRef} className="relative pr-1.5">
        <button
          type="button"
          disabled={isMutating}
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((prev) => !prev);
          }}
          aria-label="Chat options"
          className={cn(
            "flex size-7 items-center justify-center rounded-md transition-opacity hover:bg-background/80 hover:text-foreground",
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
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-foreground transition-colors hover:bg-secondary"
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
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-destructive transition-colors hover:bg-destructive/10"
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
