"use client";

import { Check, ChevronDown, FolderPlus, Layers } from "lucide-react";
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
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void workspaceActions.loadWorkspaces();
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? workspaces[0];

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;
    const id = await workspaceActions.createWorkspace(newWorkspaceName.trim());
    if (id) {
      setNewWorkspaceName("");
      setCreating(false);
      setOpen(false);
    }
  }

  if (collapsed) {
    return (
      <div className="flex justify-center px-2 py-2">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          title={activeWorkspace ? `Workspace: ${activeWorkspace.name}` : "Workspaces"}
          className="flex size-9 items-center justify-center rounded-lg border border-border/80 bg-card/60 text-foreground shadow-xs transition-colors hover:bg-secondary"
          aria-label="Switch workspace"
        >
          <Layers className="size-4 text-muted-foreground" />
        </button>
      </div>
    );
  }

  return (
    <div ref={dropdownRef} className="relative px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border/70 bg-card/60 px-2.5 text-xs font-medium text-foreground shadow-xs transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Layers className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">
            {activeWorkspace ? activeWorkspace.name : "Select Workspace"}
          </span>
        </span>
        <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-3 right-3 top-full z-40 mt-1 rounded-xl border border-border/80 bg-background/95 p-1 shadow-xl backdrop-blur-md ring-1 ring-black/5 dark:ring-white/5"
        >
          <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Workspaces
          </div>

          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {workspaces.map((ws) => {
              const isSelected = ws.id === activeWorkspaceId;
              return (
                <button
                  key={ws.id}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    void workspaceActions.selectWorkspace(ws.id);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-xs text-left transition-colors",
                    isSelected ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
                  )}
                >
                  <span className="truncate">{ws.name}</span>
                  {isSelected && <Check className="size-3.5 text-primary shrink-0 ml-2" />}
                </button>
              );
            })}
          </div>

          <div className="mt-1 border-t border-border/60 pt-1">
            {creating ? (
              <form onSubmit={handleCreate} className="p-1.5">
                <input
                  type="text"
                  autoFocus
                  placeholder="Workspace name..."
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  className="h-7 w-full rounded border border-border bg-background px-2 text-xs text-foreground outline-none focus:border-ring"
                />
                <div className="mt-1.5 flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => setCreating(false)}
                    className="rounded px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground hover:opacity-90"
                  >
                    Create
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
