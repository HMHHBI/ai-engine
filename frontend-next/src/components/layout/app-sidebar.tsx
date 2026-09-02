"use client";

import {
  ChevronLeft,
  ChevronRight,
  LogOut,
  MessageSquare,
  Moon,
  Plus,
  Settings,
  Sun,
  X,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

import { IconButton } from "@/components/ui/icon-button";
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

  const isDark = resolvedTheme === "dark";

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] md:hidden"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col",
          "border-r border-border bg-background",
          "transition-[width,transform] duration-200 ease-out",
          "md:relative md:z-auto md:translate-x-0",
          collapsed ? "md:w-16" : "md:w-64",
          mobileOpen ? "translate-x-0 w-72" : "-translate-x-full",
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
            <IconButton label="Close sidebar" onClick={onCloseMobile}>
              <X className="size-4" />
            </IconButton>
          </div>
        </div>

        {/* New chat */}
        <div className="p-3">
          <button
            type="button"
            onClick={async () => {
              try {
                const newId = await chatSessionActions.createChat();
                onCloseMobile();
                router.push(`/dashboard/chat/${newId}`);
              } catch {
                // Keep gracefully on current view
              }
            }}
            className={cn(
              "flex w-full items-center rounded-lg",
              "bg-primary text-primary-foreground",
              "text-sm font-medium",
              "transition-opacity hover:opacity-90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              collapsed
                ? "justify-center px-0 h-10"
                : "justify-start gap-2 px-3 h-10",
            )}
          >
            <Plus className="size-4 shrink-0" />
            {!collapsed && <span>New chat</span>}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3">
          <div className="space-y-1">
            <button
              type="button"
              className={cn(
                "flex h-10 w-full items-center rounded-lg",
                "bg-secondary text-foreground",
                "text-sm",
                collapsed ? "justify-center" : "gap-3 px-3",
              )}
            >
              <MessageSquare className="size-4 shrink-0" />
              {!collapsed && <span>Chats</span>}
            </button>
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
