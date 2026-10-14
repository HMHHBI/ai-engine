"use client";

import { useEffect, useState } from "react";
import { FileText, Plus, Trash2, Loader2, AlertCircle } from "lucide-react";

import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { apiClient } from "@/lib/api/client";
import type { Document as ApiDocument } from "@/types/api";
import type { WorkspaceDocument } from "@/types/workspace";
import { cn } from "@/lib/utils";

interface WorkspaceDocumentManagerProps {
  workspaceId: number;
  className?: string;
}

export function WorkspaceDocumentManager({
  workspaceId,
  className,
}: WorkspaceDocumentManagerProps) {
  const attachedDocs = useWorkspaceStore(
    (state) => state.documentsByWorkspace?.[workspaceId] ?? [],
  );
  const isLoading = useWorkspaceStore((state) => state.isLoading);
  const error = useWorkspaceStore((state) => state.error);

  const [allAvailableDocs, setAllAvailableDocs] = useState<ApiDocument[]>([]);
  const [selectedToAttach, setSelectedToAttach] = useState<number[]>([]);
  const [isAttaching, setIsAttaching] = useState(false);

  useEffect(() => {
    void workspaceActions.loadDocuments(workspaceId);

    // Fetch user documents to allow attaching
    apiClient
      .get<ApiDocument[]>("/documents")
      .then((docs) => setAllAvailableDocs(docs))
      .catch(() => {});
  }, [workspaceId]);

  const attachedIds = new Set(attachedDocs.map((d: WorkspaceDocument) => d.document_id));
  const unattachedDocs = allAvailableDocs.filter((d) => !attachedIds.has(d.id));

  function toggleSelectToAttach(id: number) {
    setSelectedToAttach((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id],
    );
  }

  async function handleAttach() {
    if (selectedToAttach.length === 0 || isAttaching) return;
    setIsAttaching(true);
    try {
      await workspaceActions.attachDocuments(workspaceId, selectedToAttach);
      setSelectedToAttach([]);
    } catch {
      // Handled in store
    } finally {
      setIsAttaching(false);
    }
  }

  async function handleDetach(docId: number) {
    try {
      await workspaceActions.detachDocument(workspaceId, docId);
    } catch {
      // Handled in store
    }
  }

  return (
    <div className={cn("flex flex-col gap-4 p-4", className)} data-testid="workspace-document-manager">
      <div className="flex items-center justify-between border-b border-border/70 pb-3">
        <h3 className="text-sm font-semibold text-foreground">Workspace Documents</h3>
        <span className="text-xs text-muted-foreground">{attachedDocs.length} attached</span>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-2.5 text-xs text-destructive">
          <AlertCircle className="size-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Attached list */}
      <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto">
        {attachedDocs.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No documents attached yet.
          </p>
        ) : (
          attachedDocs.map((doc: WorkspaceDocument) => (
            <div
              key={doc.document_id}
              className="flex items-center justify-between rounded-lg border border-border/60 bg-card/60 px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="size-3.5 text-muted-foreground shrink-0" />
                <span className="truncate font-medium text-foreground">{doc.filename}</span>
              </div>
              <button
                type="button"
                onClick={() => handleDetach(doc.document_id)}
                disabled={isLoading}
                aria-label={`Detach ${doc.filename}`}
                className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Attach more section */}
      {unattachedDocs.length > 0 && (
        <div className="mt-2 flex flex-col gap-2 border-t border-border/60 pt-3">
          <span className="text-xs font-semibold text-muted-foreground">Attach Documents</span>
          <div className="max-h-36 overflow-y-auto space-y-1">
            {unattachedDocs.map((doc) => (
              <label
                key={doc.id}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs cursor-pointer transition-colors",
                  selectedToAttach.includes(doc.id)
                    ? "border-primary/50 bg-primary/5 text-foreground"
                    : "border-border/60 hover:bg-muted/40 text-muted-foreground",
                )}
              >
                <input
                  type="checkbox"
                  checked={selectedToAttach.includes(doc.id)}
                  onChange={() => toggleSelectToAttach(doc.id)}
                  className="size-3 rounded border-border text-primary focus:ring-primary"
                />
                <span className="truncate">{doc.filename}</span>
              </label>
            ))}
          </div>

          <button
            type="button"
            onClick={handleAttach}
            disabled={selectedToAttach.length === 0 || isAttaching}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/80 disabled:opacity-50 transition-colors"
          >
            {isAttaching ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            <span>Attach Selected ({selectedToAttach.length})</span>
          </button>
        </div>
      )}
    </div>
  );
}
