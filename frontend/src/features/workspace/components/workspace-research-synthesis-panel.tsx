"use client";

import { useEffect, useState } from "react";
import {
  Sparkles,
  Download,
  AlertCircle,
  FileText,
  Loader2,
  CheckCircle2,
  Clock,
  BookmarkCheck,
  History,
  Layers,
  BarChart3,
  Search,
  AlertTriangle,
  Lightbulb,
} from "lucide-react";

import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { workspaceService } from "../services/workspace-service";
import type { ResearchRun, ResearchStatus, ResearchFacets } from "@/types/research";
import type { WorkspaceDocument } from "@/types/workspace";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkspaceResearchSynthesisPanelProps {
  workspaceId: number;
  className?: string;
  onCitationNavigate?: (target: PdfNavigationTarget) => void;
}

const EMPTY_DOCS: WorkspaceDocument[] = [];
const EMPTY_RUNS: ResearchRun[] = [];

const FACET_CONFIG: Array<{
  key: keyof ResearchFacets;
  label: string;
  icon: typeof Sparkles;
  accentClass: string;
}> = [
  {
    key: "methodology",
    label: "Methodology",
    icon: Layers,
    accentClass: "border-blue-500/20 bg-blue-500/5 text-blue-600 dark:text-blue-400",
  },
  {
    key: "datasets",
    label: "Datasets",
    icon: Search,
    accentClass: "border-purple-500/20 bg-purple-500/5 text-purple-600 dark:text-purple-400",
  },
  {
    key: "metrics",
    label: "Metrics & Evaluation",
    icon: BarChart3,
    accentClass: "border-emerald-500/20 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400",
  },
  {
    key: "findings",
    label: "Key Findings & Consensus",
    icon: Lightbulb,
    accentClass: "border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400",
  },
  {
    key: "limitations",
    label: "Limitations & Gaps",
    icon: AlertTriangle,
    accentClass: "border-rose-500/20 bg-rose-500/5 text-rose-600 dark:text-rose-400",
  },
];


function getPersistedRunId(workspaceId: number): number | null {
  if (typeof window === "undefined" || !workspaceId || workspaceId <= 0) return null;
  try {
    const raw =
      window.sessionStorage.getItem(`active_research_run_${workspaceId}`) ||
      window.localStorage.getItem(`active_research_run_${workspaceId}`);
    if (!raw) return null;
    const parsed = parseInt(raw, 10);
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

function persistRunId(workspaceId: number, runId: number | null) {
  if (typeof window === "undefined" || !workspaceId || workspaceId <= 0) return;
  try {
    if (runId !== null) {
      window.sessionStorage.setItem(`active_research_run_${workspaceId}`, String(runId));
      window.localStorage.setItem(`active_research_run_${workspaceId}`, String(runId));
    } else {
      window.sessionStorage.removeItem(`active_research_run_${workspaceId}`);
      window.localStorage.removeItem(`active_research_run_${workspaceId}`);
    }
  } catch {
    // Ignore storage errors
  }
}

export function WorkspaceResearchSynthesisPanel({
  workspaceId,
  className,
  onCitationNavigate,
}: WorkspaceResearchSynthesisPanelProps) {
  const documents = useWorkspaceStore(
    (state) => state.documentsByWorkspace?.[workspaceId] ?? EMPTY_DOCS,
  );
  const runs = useWorkspaceStore(
    (state) => state.researchRunsByWorkspace?.[workspaceId] ?? EMPTY_RUNS,
  );
  const isLoading = useWorkspaceStore((state) => state.isLoading);
  const error = useWorkspaceStore((state) => state.error);

  const [prevWorkspaceId, setPrevWorkspaceId] = useState(workspaceId);
  const [query, setQuery] = useState("");
  const [rawSelectedDocIds, setRawSelectedDocIds] = useState<number[]>([]);
  const [latestRun, setLatestRun] = useState<ResearchRun | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(() => getPersistedRunId(workspaceId));
  const [showHistory, setShowHistory] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<"markdown" | "json" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [syncedRunId, setSyncedRunId] = useState<number | null>(null);

  // Synchronously handle workspace transition without wiping persisted run if it belongs to current workspace
  if (prevWorkspaceId !== workspaceId) {
    setPrevWorkspaceId(workspaceId);
    setLatestRun(null);
    const restored = getPersistedRunId(workspaceId);
    setSelectedRunId(restored);
    setRawSelectedDocIds([]);
    setQuery("");
    setSyncedRunId(null);
  }

  // Load runs on mount or workspace switch
  useEffect(() => {
    if (workspaceId > 0) {
      void workspaceActions.loadResearchRuns(workspaceId);
    }
  }, [workspaceId]);

  // Persist selectedRunId whenever it changes
  useEffect(() => {
    if (workspaceId > 0) {
      persistRunId(workspaceId, selectedRunId);
    }
  }, [selectedRunId, workspaceId]);

  // Only ready documents can be selected for synthesis
  const safeDocs = Array.isArray(documents) ? documents : [];
  const readyDocs = safeDocs.filter((doc) => doc.status === "ready");
  const readyDocIdSet = new Set(readyDocs.map((doc) => doc.document_id));

  // Keep active selection valid and enforce 20-paper maximum
  const selectedDocIds = (
    Array.isArray(rawSelectedDocIds) ? rawSelectedDocIds : []
  )
    .filter((id) => readyDocIdSet.has(id))
    .slice(0, 20);

  const isFormValid =
    query.trim().length > 0 &&
    selectedDocIds.length >= 2 &&
    selectedDocIds.length <= 20;

  // Derive active run safely: selected history run > newly triggered run > fallback to head
  const activeRun: ResearchRun | null =
    (latestRun && latestRun.workspace_id === workspaceId && (selectedRunId === null || selectedRunId === latestRun.id) ? latestRun : null) ??
    (selectedRunId !== null ? runs.find((r) => r.id === selectedRunId) : null) ??
    (runs[0] ?? null);

  // If a run is persisted or explicitly selected, ensure selectedRunId tracks it
  const persistedId = getPersistedRunId(workspaceId);
  const effectiveRunId = selectedRunId ?? persistedId;

  // Sync form inputs only when an explicit run matches current workspace's runs
  const targetRunToSync = effectiveRunId !== null ? (runs.find((r) => r.id === effectiveRunId) ?? null) : null;
  if (targetRunToSync && targetRunToSync.id !== syncedRunId) {
    setSyncedRunId(targetRunToSync.id);
    if (selectedRunId !== targetRunToSync.id) {
      setSelectedRunId(targetRunToSync.id);
    }
    setQuery(targetRunToSync.query);
    const savedIds = targetRunToSync.run_metadata?.selected_document_ids;
    if (Array.isArray(savedIds)) {
      setRawSelectedDocIds(
        savedIds.filter(
          (id): id is number => typeof id === "number" && Number.isInteger(id)
        )
      );
    }
  }

  function toggleDocSelection(docId: number) {
    if (!readyDocIdSet.has(docId)) return;

    setRawSelectedDocIds((prev) => {
      const current = prev
        .filter((id) => readyDocIdSet.has(id))
        .slice(0, 20);

      if (current.includes(docId)) {
        return current.filter((id) => id !== docId);
      }

      if (current.length >= 20) {
        return current;
      }

      return [...current, docId];
    });
  }

  function selectAllDocs() {
    setRawSelectedDocIds(
      readyDocs.slice(0, 20).map((doc) => doc.document_id),
    );
  }

  function clearDocSelection() {
    setRawSelectedDocIds([]);
  }

  async function handleRunSynthesis(e: React.FormEvent) {
    e.preventDefault();
    if (!isFormValid || isLoading) return;

    try {
      const result = await workspaceActions.triggerResearchSynthesis(workspaceId, {
        query: query.trim(),
        document_ids: selectedDocIds,
      });
      setLatestRun(result);
      setSelectedRunId(result.id);
      setQuery("");
    } catch {
      // Store captures error
    }
  }

  async function handleExport(format: "markdown" | "json") {
    if (!activeRun) return;
    setExportingFormat(format);
    setExportError(null);
    try {
      await workspaceService.downloadResearchExport(workspaceId, activeRun.id, format);
    } catch (err) {
      setExportError(
        err instanceof Error
          ? err.message
          : `Failed to export research results as ${format.toUpperCase()}.`,
      );
    } finally {
      setExportingFormat(null);
    }
  }

  function renderStatusBadge(status: ResearchStatus) {
    switch (status) {
      case "completed":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="size-4" />
            <span>Completed</span>
          </span>
        );
      case "running":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 dark:text-blue-400">
            <Loader2 className="size-4 animate-spin" />
            <span>Running</span>
          </span>
        );
      case "queued":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            <Clock className="size-4" />
            <span>Queued</span>
          </span>
        );
      case "failed":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-destructive">
            <AlertCircle className="size-4" />
            <span>Failed</span>
          </span>
        );
    }
  }

  return (
    <div className={cn("flex flex-col gap-6 p-4 md:p-6", className)} data-testid="research-synthesis-panel">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/70 pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Sparkles className="size-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">Cross-Document Research Synthesis</h2>
          </div>
          <p className="text-xs text-muted-foreground">
            Select 2 to 20 ready documents to generate a structured 5-facet comparative synthesis with verified citations.
          </p>
        </div>

        {runs.length > 0 && (
          <button
            type="button"
            onClick={() => setShowHistory((prev) => !prev)}
            data-testid="toggle-history-button"
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
              showHistory
                ? "border-primary bg-primary/10 text-primary"
                : "border-border/70 bg-background hover:bg-muted/40 text-muted-foreground",
            )}
          >
            <History className="size-3.5" />
            <span>Past Runs ({runs.length})</span>
          </button>
        )}
      </div>

      {/* History Drawer / Selector */}
      {showHistory && runs.length > 0 && (
        <div
          data-testid="research-runs-history"
          className="flex flex-col gap-2 rounded-xl border border-border/70 bg-card/70 p-3 shadow-xs"
        >
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Run History
          </span>
          <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
            {runs.map((run) => (
              <button
                key={run.id}
                type="button"
                onClick={() => {
                  setSelectedRunId(run.id);
                  persistRunId(workspaceId, run.id);
                  setQuery(run.query);

                  const savedIds = run.run_metadata?.selected_document_ids;
                  setRawSelectedDocIds(
                    Array.isArray(savedIds)
                      ? savedIds.filter(
                          (id): id is number =>
                            typeof id === "number" && Number.isInteger(id),
                        )
                      : [],
                  );

                  setShowHistory(false);
                }}
                className={cn(
                  "flex items-center justify-between gap-3 rounded-lg border p-2 text-left text-xs transition-colors",
                  activeRun?.id === run.id
                    ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                    : "border-border/50 bg-background/50 hover:bg-muted/30 text-muted-foreground",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-foreground">
                    #{run.id}: {run.query}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {new Date(run.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="shrink-0">{renderStatusBadge(run.status)}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Synthesis Configuration Form */}
      <form onSubmit={handleRunSynthesis} className="flex flex-col gap-4 rounded-xl border border-border/70 bg-card/60 p-4 shadow-xs">
        {/* Document Selection Section */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Workspace Documents ({selectedDocIds.length} / {readyDocs.length} ready papers selected)
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAllDocs}
                disabled={readyDocs.length === 0}
                className="text-[11px] text-primary hover:underline disabled:opacity-50"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={clearDocSelection}
                disabled={selectedDocIds.length === 0}
                className="text-[11px] text-muted-foreground hover:underline disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>

          {readyDocs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              No ready documents are available. Wait for document processing to finish.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-40 overflow-y-auto pr-1">
              {readyDocs.map((doc: WorkspaceDocument) => {
                const checked = selectedDocIds.includes(doc.document_id);
                return (
                  <label
                    key={doc.document_id}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg border p-2 text-xs cursor-pointer transition-colors",
                      checked
                        ? "border-primary/50 bg-primary/5 text-foreground font-medium"
                        : "border-border/60 hover:bg-muted/40 text-muted-foreground",
                    )}
                  >
                    <input
                      type="checkbox"
                      data-testid={`doc-select-checkbox-${doc.document_id}`}
                      checked={checked}
                      onChange={() => toggleDocSelection(doc.document_id)}
                      className="size-3.5 rounded border-border text-primary focus:ring-primary"
                    />
                    <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{doc.filename}</span>
                  </label>
                );
              })}
            </div>
          )}

          {selectedDocIds.length > 0 && selectedDocIds.length < 2 && (
            <span className="text-[11px] text-amber-500 font-medium">
              * Minimum 2 documents required for synthesis.
            </span>
          )}

          {selectedDocIds.length === 20 && readyDocs.length > 20 && (
            <span className="text-[11px] text-amber-500 font-medium">
              Maximum 20 papers per synthesis. Clear a selection to choose different papers.
            </span>
          )}
        </div>

        {/* Prompt Input */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="synthesis-query" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Synthesis Query / Hypothesis
          </label>
          <textarea
            id="synthesis-query"
            rows={3}
            placeholder="e.g. Compare the methodologies, datasets, and benchmark metrics across these papers..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={isLoading}
            className="w-full resize-none rounded-lg border border-border bg-background p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          />
        </div>

        {/* Trigger Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!isFormValid || isLoading}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow-xs transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>Synthesizing...</span>
              </>
            ) : (
              <>
                <Sparkles className="size-3.5" />
                <span>Run Synthesis</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Synthesis Output & Citations */}
      {activeRun && (
        <div className="flex flex-col gap-4 rounded-xl border border-border/70 bg-card/40 p-4 shadow-xs" data-testid="research-run-result">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/60 pb-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-foreground">
                Run #{activeRun.id} Output
              </span>
              {renderStatusBadge(activeRun.status)}
            </div>

            {/* Export Actions */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleExport("markdown")}
                disabled={exportingFormat !== null || activeRun.status !== "completed"}
                className="flex items-center gap-1.5 rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground hover:bg-secondary disabled:opacity-50"
              >
                {exportingFormat === "markdown" ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Download className="size-3" />
                )}
                <span>Export Markdown</span>
              </button>
              <button
                type="button"
                onClick={() => handleExport("json")}
                disabled={exportingFormat !== null || activeRun.status !== "completed"}
                className="flex items-center gap-1.5 rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground hover:bg-secondary disabled:opacity-50"
              >
                {exportingFormat === "json" ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Download className="size-3" />
                )}
                <span>Export JSON</span>
              </button>
            </div>
          </div>

          {exportError && (
            <div className="flex items-center justify-between rounded-lg bg-destructive/10 p-2.5 text-xs text-destructive">
              <div className="flex items-center gap-2">
                <AlertCircle className="size-3.5 shrink-0" />
                <span>{exportError}</span>
              </div>
              <button
                type="button"
                onClick={() => setExportError(null)}
                className="text-[11px] underline hover:no-underline"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* 5-Facet Comparative View or Fallback Synthesized Answer */}
          {activeRun.status === "failed" ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
              {activeRun.error_message || "Synthesis run encountered an error and could not be completed."}
            </div>
          ) : (
            <div className="flex flex-col gap-3" data-testid="structured-facets-container">
              {FACET_CONFIG.map(({ key, label, icon: Icon, accentClass }) => {
                const rawFacets = typeof activeRun.facets === "string"
                  ? (() => { try { return JSON.parse(activeRun.facets); } catch { return null; } })()
                  : activeRun.facets;
                const content = rawFacets?.[key] || (key === "methodology" ? activeRun.answer : null);
                if (!content) return null;
                return (
                  <div
                    key={key}
                    data-testid={`facet-card-${key}`}
                    className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background/60 p-3"
                  >
                    <div className="flex items-center gap-2">
                      <span className={cn("flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold border", accentClass)}>
                        <Icon className="size-3" />
                        <span>{label}</span>
                      </span>
                    </div>
                    <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed text-foreground whitespace-pre-wrap pl-1">
                      {content}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Citations List */}
          {activeRun.citations && activeRun.citations.length > 0 && (
            <div className="mt-3 flex flex-col gap-2 border-t border-border/60 pt-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <BookmarkCheck className="size-3.5 text-primary" />
                Citations & Evidence ({activeRun.citations.length})
              </span>
              <div className="flex flex-col gap-2">
                {activeRun.citations.map((cite) => {
                  const targetPage = cite.page_number ?? 1;
                  const canNavigate = Boolean(onCitationNavigate && cite.document_id);
                  const handleNav = () => {
                    if (canNavigate && cite.document_id) {
                      onCitationNavigate?.({
                        documentId: cite.document_id,
                        pageNumber: targetPage,
                        requestId: Date.now(),
                      });
                    }
                  };

                  return (
                    <button
                      key={cite.citation_id}
                      type="button"
                      disabled={!canNavigate}
                      onClick={handleNav}
                      aria-label={`Open ${cite.filename} at page ${targetPage}`}
                      data-testid={`citation-item-${cite.citation_id}`}
                      className={cn(
                        "flex flex-col gap-1 rounded-lg border border-border/60 bg-muted/20 p-2.5 text-left text-xs transition-colors w-full",
                        canNavigate && "hover:border-primary/50 hover:bg-muted/40 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                      )}
                    >
                      <div className="flex items-center justify-between text-[11px] font-medium text-foreground w-full">
                        <span className="truncate flex items-center gap-1.5">
                          [{cite.citation_id}] {cite.filename}
                          {canNavigate && <ExternalLink className="size-3 text-primary shrink-0" aria-hidden="true" />}
                        </span>
                        {cite.page_number && (
                          <span className="text-muted-foreground font-mono shrink-0">Page {cite.page_number}</span>
                        )}
                      </div>
                      <blockquote className="border-l-2 border-primary/60 pl-2 text-muted-foreground italic text-[11px] text-left">
                        &ldquo;{cite.excerpt}&rdquo;
                      </blockquote>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
