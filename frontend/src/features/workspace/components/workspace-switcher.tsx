"use client";

import { Check, ChevronDown, FolderPlus, Layers, Loader2, AlertCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { cn } from "@/lib/utils";

interface WorkspaceSwitcherProps {
  collapsed?: boolean;
}

export function WorkspaceSwitcher({ collapsed = false }: WorkspaceSwitcherProps) {
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const isLoading = useWorkspaceStore((state) => state.isLoading);
  const error = useWorkspaceStore((state) => state.error);

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void workspaceActions.loadWorkspaces();
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && open) {
        setOpen(false);
        setCreating(false);
      }
    }
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }

    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? workspaces[0];

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newWorkspaceName.trim();
    if (!name) return;
    const id = await workspaceActions.createWorkspace(name);
    if (id) {
      setNewWorkspaceName("");
      setCreating(false);
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className={cn("relative", collapsed ? "px-2 py-2 flex justify-center" : "px-3 py-2")}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={activeWorkspace ? `Workspace: ${activeWorkspace.name}` : "Workspaces"}
        disabled={isLoading && workspaces.length === 0}
        className={cn(
          "flex items-center justify-between rounded-lg border border-border/70 bg-card/60 text-xs font-medium text-foreground shadow-xs transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
          collapsed ? "size-9 justify-center p-0" : "h-9 w-full gap-2 px-2.5",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          {isLoading ? (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
          ) : (
            <Layers className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          {!collapsed && (
            <span className="truncate">
              {activeWorkspace ? activeWorkspace.name : "Select Workspace"}
            </span>
          )}
        </span>
        {!collapsed && (
          <ChevronDown
            className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Workspaces"
          className={cn(
            "absolute z-50 mt-1 rounded-xl border border-border/80 bg-background/95 p-1.5 shadow-xl backdrop-blur-md ring-1 ring-black/5 dark:ring-white/5",
            collapsed ? "left-12 top-0 w-56" : "left-3 right-3 top-full",
          )}
        >
          <div className="flex items-center justify-between px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Workspaces</span>
            {isLoading && <Loader2 className="size-3 animate-spin" />}
          </div>

          {error && (
            <div className="mx-1 mb-1.5 flex items-center gap-1.5 rounded-md bg-destructive/10 p-1.5 text-xs text-destructive">
              <AlertCircle className="size-3.5 shrink-0" />
              <span className="truncate">{error}</span>
            </div>
          )}

          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {workspaces.length === 0 && !isLoading ? (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                No workspaces available.
              </p>
            ) : (
              workspaces.map((ws) => {
                const isSelected = ws.id === activeWorkspaceId;
                return (
                  <button
                    key={ws.id}
                    type="button"
                    onClick={() => {
                      void workspaceActions.selectWorkspace(ws.id);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-xs text-left transition-colors",
                      isSelected
                        ? "bg-secondary font-medium text-foreground"
                        : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
                    )}
                  >
                    <span className="truncate">{ws.name}</span>
                    {isSelected && <Check className="size-3.5 text-primary shrink-0 ml-2" />}
                  </button>
                );
              })
            )}
          </div>

          <div className="mt-1 border-t border-border/60 pt-1">
            {creating ? (
              <form onSubmit={handleCreate} className="p-1 space-y-1.5">
                <label htmlFor="workspace-name-input" className="sr-only">
                  Workspace name
                </label>
                <input
                  id="workspace-name-input"
                  type="text"
                  autoFocus
                  placeholder="Workspace name..."
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  disabled={isLoading}
                  className="h-7 w-full rounded border border-border bg-background px-2 text-xs text-foreground outline-none focus:border-ring disabled:opacity-50"
                />
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => setCreating(false)}
                    disabled={isLoading}
                    className="rounded px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isLoading || !newWorkspaceName.trim()}
                    className="rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    {isLoading ? "Creating..." : "Create"}
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <FolderPlus className="size-3.5" />
                <span>New workspace</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
