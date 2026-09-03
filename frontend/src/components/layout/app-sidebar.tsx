"use client";

import {
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  LogOut,
  MessageSquare,
  Moon,
  Plus,
  Settings,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

import { IconButton } from "@/components/ui/icon-button";
import { ChatHistoryList } from "@/features/chat/components/chat-history-list";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { authActions } from "@/features/auth/actions/auth-actions";
import { useAuthStore } from "@/features/auth";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapse: () => void;
  onCloseMobile: () => void;
}

export function AppSidebar({
  collapsed,
  mobileOpen,
  onToggleCollapse,
  onCloseMobile,
}: AppSidebarProps) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const user = useAuthStore((state) => state.user);
  const [isCreatingChat, setIsCreatingChat] = useState(false);

  const sidebarRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const isDark = resolvedTheme === "dark";

  // Escape key listener and focus management for mobile drawer
  useEffect(() => {
    if (!mobileOpen) return;

    // Move initial focus to the close button inside drawer
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseMobile();
        return;
      }

      // Trap Tab focus inside mobile drawer
      if (event.key === "Tab" && sidebarRef.current) {
        const focusableElements =
          sidebarRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
          );

        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (event.shiftKey && document.activeElement === firstElement) {
          event.preventDefault();
          lastElement.focus();
        } else if (!event.shiftKey && document.activeElement === lastElement) {
          event.preventDefault();
          firstElement.focus();
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileOpen, onCloseMobile]);

  async function handleNewChat() {
    if (isCreatingChat) return;

    setIsCreatingChat(true);
    try {
      const newId = await chatSessionActions.createChat();
      onCloseMobile();
      router.push(`/dashboard/chat/${newId}`);
    } catch {
      // Keep gracefully on current view
    } finally {
      setIsCreatingChat(false);
    }
  }

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] md:hidden"
          onClick={onCloseMobile}
        />
      )}

      <aside
        ref={sidebarRef}
        role={mobileOpen ? "dialog" : undefined}
        aria-modal={mobileOpen ? "true" : undefined}
        aria-label={mobileOpen ? "Navigation sidebar" : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col",
          "border-r border-border bg-background",
          "transition-[width,transform] duration-200 ease-out",
          "md:relative md:z-auto md:translate-x-0",
          collapsed ? "md:w-16" : "md:w-64",
          mobileOpen
            ? "w-[min(18rem,calc(100vw-2.5rem))] translate-x-0"
            : "-translate-x-full",
        )}
      >
        {/* Brand */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center border-b border-border px-3",
            collapsed ? "justify-center" : "justify-between",
          )}
        >
          {!collapsed && (
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <span className="text-sm font-semibold">H</span>
              </div>

              <span className="truncate text-sm font-semibold">AI Engine</span>
            </div>
          )}

          {collapsed && (
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <span className="text-sm font-semibold">H</span>
            </div>
          )}

          <div className="md:hidden">
            <IconButton
              ref={closeButtonRef}
              label="Close sidebar"
              onClick={onCloseMobile}
              className="size-9"
            >
              <X className="size-4" />
            </IconButton>
          </div>
        </div>

        {/* New chat */}
        <div className="p-3">
          <button
            type="button"
            disabled={isCreatingChat}
            onClick={() => void handleNewChat()}
            className={cn(
              "flex w-full items-center rounded-lg",
              "bg-primary text-primary-foreground",
              "text-sm font-medium",
              "transition-opacity hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:pointer-events-none disabled:opacity-50",
              collapsed
                ? "justify-center px-0 h-10"
                : "justify-start gap-2 px-3 h-10",
            )}
          >
            {isCreatingChat ? (
              <LoaderCircle className="size-4 shrink-0 animate-spin" />
            ) : (
              <Plus className="size-4 shrink-0" />
            )}
            {!collapsed && (
              <span>{isCreatingChat ? "Creating..." : "New chat"}</span>
            )}
          </button>
        </div>

        {/* Chat history */}
        <nav
          aria-label="Chat history"
          className="min-h-0 flex-1 overflow-y-auto px-3"
        >
          <div className="space-y-2">
            <div
              className={cn(
                "flex h-10 items-center rounded-lg",
                "text-sm text-muted-foreground",
                collapsed ? "justify-center" : "gap-3 px-3",
              )}
            >
              <MessageSquare className="size-4 shrink-0" />

              {!collapsed && <span className="font-medium">Chats</span>}
            </div>

            {!collapsed && <ChatHistoryList onSelectChat={onCloseMobile} />}
          </div>
        </nav>

        {/* Bottom controls */}
        <div className="space-y-1 border-t border-border p-3">
          <button
            type="button"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className={cn(
              "flex h-10 w-full items-center rounded-lg",
              "text-sm text-muted-foreground",
              "transition-colors hover:bg-secondary hover:text-foreground",
              collapsed ? "justify-center" : "gap-3 px-3",
            )}
          >
            {isDark ? (
              <Sun className="size-4 shrink-0" />
            ) : (
              <Moon className="size-4 shrink-0" />
            )}

            {!collapsed && <span>{isDark ? "Light mode" : "Dark mode"}</span>}
          </button>

          <button
            type="button"
            className={cn(
              "flex h-10 w-full items-center rounded-lg",
              "text-sm text-muted-foreground",
              "transition-colors hover:bg-secondary hover:text-foreground",
              collapsed ? "justify-center" : "gap-3 px-3",
            )}
          >
            <Settings className="size-4 shrink-0" />
            {!collapsed && <span>Settings</span>}
          </button>

          <button
            type="button"
            onClick={() => authActions.logout()}
            className={cn(
              "flex h-10 w-full items-center rounded-lg",
              "text-sm text-destructive",
              "transition-colors hover:bg-destructive/10 hover:text-destructive",
              collapsed ? "justify-center" : "gap-3 px-3",
            )}
          >
            <LogOut className="size-4 shrink-0" />
            {!collapsed && <span>Log out</span>}
          </button>

          {/* User */}
          <div
            className={cn(
              "mt-2 flex items-center rounded-lg border border-border p-2",
              collapsed ? "justify-center" : "gap-2",
            )}
          >
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium">
              {user?.name?.charAt(0).toUpperCase() ?? "H"}
            </div>

            {!collapsed && (
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {user?.name ?? "User"}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {user?.email ?? ""}
                </p>
              </div>
            )}
          </div>

          {/* Desktop collapse */}
          <div className="hidden pt-1 md:block">
            <button
              type="button"
              onClick={onToggleCollapse}
              className={cn(
                "flex h-9 w-full items-center rounded-lg",
                "text-xs text-muted-foreground",
                "transition-colors hover:bg-secondary hover:text-foreground",
                collapsed ? "justify-center" : "justify-start gap-2 px-3",
              )}
            >
              {collapsed ? (
                <ChevronRight className="size-4" />
              ) : (
                <>
                  <ChevronLeft className="size-4" />
                  <span>Collapse sidebar</span>
                </>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
