"use client";

import { useRef,  useEffect, useState } from "react";
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
  RotateCcw,
  Square,
  Ban,
} from "lucide-react";

import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { workspaceService } from "../services/workspace-service";
import { ACTIVE_RESEARCH_STATUSES, type ResearchRun, type ResearchStatus, type ResearchFacets } from "@/types/research";
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

const LIFECYCLE_STAGES: ReadonlyArray<{
  key: ResearchStatus;
  label: string;
}> = [
  { key: "queued", label: "Queued" },
  { key: "retrieving", label: "Retrieving" },
  { key: "synthesizing", label: "Synthesizing" },
  { key: "validating", label: "Validating" },
  { key: "completed", label: "Completed" },
];

const STAGE_ORDER: Record<ResearchStatus, number> = {
  queued: 0,
  running: 1,
  retrieving: 1,
  synthesizing: 2,
  validating: 3,
  completed: 4,
  failed: 4,
  cancelled: 4,
};

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
  const runsForWorkspace = useWorkspaceStore(
    (state) => state.researchRunsByWorkspace?.[workspaceId],
  );
  const runsLoaded = runsForWorkspace !== undefined;
  const runs = runsForWorkspace ?? EMPTY_RUNS;
  const isLoading = useWorkspaceStore((state) => state.isLoading);
  const error = useWorkspaceStore((state) => state.error);

  const [query, setQuery] = useState("");
  const [rawSelectedDocIds, setRawSelectedDocIds] = useState<number[]>([]);
  const [latestRun, setLatestRun] = useState<ResearchRun | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(() => getPersistedRunId(workspaceId));
  const [showHistory, setShowHistory] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<"markdown" | "json" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [syncedRunId, setSyncedRunId] = useState<number | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [liveStageOverride, setLiveStageOverride] = useState<{
    runId: number;
    status: ResearchStatus;
    progressPercent: number;
    cancelRequested: boolean;
    errorMessage?: string | null;
  } | null>(null);
  const prevWorkspaceIdRef = useRef(workspaceId);

  // Reset form inputs and local state when workspaceId prop changes on the same instance
  useEffect(() => {
    if (prevWorkspaceIdRef.current !== workspaceId) {
      prevWorkspaceIdRef.current = workspaceId;
      setQuery("");
      setRawSelectedDocIds([]);
      setLatestRun(null);
      setSyncedRunId(null);
      setLiveStageOverride(null);
      setSelectedRunId(getPersistedRunId(workspaceId));
    }
  }, [workspaceId]);

  // Load runs on mount or workspace switch
  useEffect(() => {
    if (workspaceId > 0) {
      void workspaceActions.loadResearchRuns(workspaceId);
    }
  }, [workspaceId]);

  // Validate persisted run once runs are fetched; clear invalid run ID from storage and state
  useEffect(() => {
    if (!runsLoaded || selectedRunId === null) return;
    const exists = runs.some((r) => r.id === selectedRunId);
    if (!exists) {
      persistRunId(workspaceId, null);
      queueMicrotask(() => {
        setSelectedRunId((prev) => (prev === selectedRunId ? null : prev));
      });
    }
  }, [runsLoaded, runs, selectedRunId, workspaceId]);

  // Persist selectedRunId only when it matches an authentic run of this workspace, or clear when null
  useEffect(() => {
    if (workspaceId <= 0 || !runsLoaded) return;
    if (selectedRunId !== null) {
      if (runs.some((r) => r.id === selectedRunId)) {
        persistRunId(workspaceId, selectedRunId);
      }
    } else {
      persistRunId(workspaceId, null);
    }
  }, [selectedRunId, workspaceId, runsLoaded, runs]);

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
  const rawActiveRun: ResearchRun | null =
    (latestRun && latestRun.workspace_id === workspaceId && (selectedRunId === null || selectedRunId === latestRun.id) ? latestRun : null) ??
    (selectedRunId !== null ? runs.find((r) => r.id === selectedRunId) : null) ??
    (runs[0] ?? null);

  const activeRun: ResearchRun | null =
    rawActiveRun &&
    liveStageOverride &&
    liveStageOverride.runId === rawActiveRun.id
      ? {
          ...rawActiveRun,
          status: liveStageOverride.status,
          error_message:
            liveStageOverride.errorMessage ?? rawActiveRun.error_message,
          run_metadata: {
            ...rawActiveRun.run_metadata,
            lifecycle: {
              ...(rawActiveRun.run_metadata?.lifecycle ?? {}),
              cancel_requested: liveStageOverride.cancelRequested,
            },
          },
        }
      : rawActiveRun;

  const isRunActive = Boolean(
    activeRun && ACTIVE_RESEARCH_STATUSES.has(activeRun.status),
  );

  const activeRunId = activeRun?.id ?? null;
  const activeRunStatus = activeRun?.status ?? null;

  // Stream SSE stage updates with polling fallback while an async run is active
  useEffect(() => {
    if (activeRunId === null || activeRunStatus === null || !ACTIVE_RESEARCH_STATUSES.has(activeRunStatus)) {
      return;
    }

    const trackedRunId = activeRunId;
    let closed = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const startPollingFallback = () => {
      if (pollTimer !== null || closed) return;
      pollTimer = setInterval(async () => {
        if (closed) return;
        const updated = await workspaceActions.refreshResearchRun(
          workspaceId,
          trackedRunId,
        );
        if (updated && !ACTIVE_RESEARCH_STATUSES.has(updated.status)) {
          setLatestRun(updated);
          setLiveStageOverride(null);
          if (pollTimer !== null) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      }, 1500);
    };

    const stopSse =
      typeof workspaceService.streamResearchRunEvents === "function"
        ? workspaceService.streamResearchRunEvents(workspaceId, trackedRunId, {
            onStage: (evt) => {
              if (closed) return;
              setLiveStageOverride({
                runId: trackedRunId,
                status: evt.status,
                progressPercent: evt.progress_percent,
                cancelRequested: evt.cancel_requested,
                errorMessage: evt.error_message,
              });
            },
            onDone: async () => {
              if (closed) return;
              const refreshed = await workspaceActions.refreshResearchRun(
                workspaceId,
                trackedRunId,
              );
              if (refreshed) {
                setLatestRun(refreshed);
              }
              setLiveStageOverride(null);
            },
            onError: () => {
              startPollingFallback();
            },
          })
        : () => {};

    if (typeof workspaceActions.refreshResearchRun === "function") {
      void workspaceActions
        .refreshResearchRun(workspaceId, trackedRunId)
        .then((refreshed) => {
          if (
            !closed &&
            refreshed &&
            !ACTIVE_RESEARCH_STATUSES.has(refreshed.status)
          ) {
            setLatestRun(refreshed);
            setLiveStageOverride(null);
          }
        });
    }

    return () => {
      closed = true;
      stopSse();
      if (pollTimer !== null) {
        clearInterval(pollTimer);
      }
    };
  }, [workspaceId, activeRunId, activeRunStatus]);

  // Sync form inputs when an explicit valid run is active
  useEffect(() => {
    if (selectedRunId === null) return;
    const matchingRun = runs.find((r) => r.id === selectedRunId);
    if (!matchingRun || matchingRun.id === syncedRunId) return;

    queueMicrotask(() => {
      setSyncedRunId(matchingRun.id);
      setQuery(matchingRun.query);
      const savedIds = matchingRun.run_metadata?.selected_document_ids;
      if (Array.isArray(savedIds)) {
        setRawSelectedDocIds(
          savedIds.filter(
            (id): id is number => typeof id === "number" && Number.isInteger(id)
          )
        );
      }
    });
  }, [selectedRunId, runs, syncedRunId]);

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

  async function handleCancelRun() {
    if (!activeRun || !isRunActive || isCancelling) return;
    setIsCancelling(true);
    try {
      const { response, run } = await workspaceActions.cancelResearchRun(
        workspaceId,
        activeRun.id,
      );
      if (run) {
        setLatestRun(run);
      }
      setLiveStageOverride({
        runId: activeRun.id,
        status: response.status,
        progressPercent: response.status === "cancelled" ? 100 : 50,
        cancelRequested: response.cancel_requested,
      });
    } finally {
      setIsCancelling(false);
    }
  }

  async function handleRetryRun() {
    if (!activeRun || isLoading) return;
    const savedIds = activeRun.run_metadata?.selected_document_ids;
    const retryDocs = Array.isArray(savedIds)
      ? savedIds.filter(
          (id): id is number => typeof id === "number" && readyDocIdSet.has(id),
        )
      : selectedDocIds;
    const targetDocs = retryDocs.length >= 2 ? retryDocs : selectedDocIds;
    if (targetDocs.length < 2) return;

    setRawSelectedDocIds(targetDocs);
    try {
      const result = await workspaceActions.triggerResearchSynthesis(workspaceId, {
        query: activeRun.query.trim(),
        document_ids: targetDocs,
      });
      setLatestRun(result);
      setSelectedRunId(result.id);
      setLiveStageOverride(null);
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
      case "retrieving":
      case "synthesizing":
      case "validating":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 dark:text-blue-400 capitalize">
            <Loader2 className="size-4 animate-spin" />
            <span>{status}</span>
          </span>
        );
      case "cancelled":
        return (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <Ban className="size-4" />
            <span>Cancelled</span>
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

            {/* Lifecycle & Export Actions */}
            <div className="flex flex-wrap items-center gap-2">
              {isRunActive && (
                <button
                  type="button"
                  data-testid="cancel-research-run-btn"
                  onClick={handleCancelRun}
                  disabled={
                    isCancelling ||
                    Boolean(activeRun.run_metadata?.lifecycle?.cancel_requested)
                  }
                  className="flex items-center gap-1.5 rounded border border-destructive/40 bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive hover:bg-destructive/15 disabled:opacity-60"
                >
                  {isCancelling ||
                  Boolean(activeRun.run_metadata?.lifecycle?.cancel_requested) ? (
                    <>
                      <Loader2 className="size-3 animate-spin" />
                      <span>Cancelling...</span>
                    </>
                  ) : (
                    <>
                      <Square className="size-3" />
                      <span>Cancel Run</span>
                    </>
                  )}
                </button>
              )}

              {(activeRun.status === "failed" ||
                activeRun.status === "cancelled") && (
                <button
                  type="button"
                  data-testid="retry-research-run-btn"
                  onClick={handleRetryRun}
                  disabled={isLoading}
                  className="flex items-center gap-1.5 rounded border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 disabled:opacity-50"
                >
                  <RotateCcw className="size-3" />
                  <span>Retry Run</span>
                </button>
              )}
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

          {/* Live Stage Progress Stepper for In-Flight Runs */}
          {isRunActive && (
            <div
              data-testid="research-stage-stepper"
              className="flex flex-col gap-2.5 rounded-lg border border-blue-500/25 bg-blue-500/5 p-3"
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-foreground">
                  {activeRun.run_metadata?.lifecycle?.cancel_requested
                    ? "Cancellation requested — stopping after current step..."
                    : `Stage: ${
                        activeRun.status.charAt(0).toUpperCase() +
                        activeRun.status.slice(1)
                      }`}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {liveStageOverride?.progressPercent ??
                    ((STAGE_ORDER[activeRun.status] ?? 0) + 1) * 20}
                  %
                </span>
              </div>
              <div className="grid grid-cols-5 gap-1.5">
                {LIFECYCLE_STAGES.map((step, index) => {
                  const currentIdx = STAGE_ORDER[activeRun.status] ?? 0;
                  const isDone = index < currentIdx;
                  const isCurrent = index === currentIdx;
                  return (
                    <div
                      key={step.key}
                      data-testid={`lifecycle-stage-${step.key}`}
                      className={cn(
                        "flex items-center justify-center gap-1 rounded border px-2 py-1 text-[11px] font-medium transition-colors",
                        isDone &&
                          "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
                        isCurrent &&
                          "border-blue-500/50 bg-blue-500/15 text-blue-600 dark:text-blue-400",
                        !isDone &&
                          !isCurrent &&
                          "border-border/50 bg-background/40 text-muted-foreground",
                      )}
                    >
                      {isCurrent && (
                        <Loader2 className="size-2.5 animate-spin shrink-0" />
                      )}
                      {isDone && (
                        <CheckCircle2 className="size-2.5 shrink-0" />
                      )}
                      <span className="truncate">{step.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 5-Facet Comparative View or Terminal Status Callout */}
          {activeRun.status === "failed" ? (
            <div className="flex flex-col gap-1 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
              <span>
                {activeRun.error_message ||
                  "Synthesis run encountered an error and could not be completed."}
              </span>
              {activeRun.run_metadata?.lifecycle?.correlation_id && (
                <span className="font-mono text-[11px] text-muted-foreground">
                  Correlation ID:{" "}
                  {activeRun.run_metadata.lifecycle.correlation_id}
                </span>
              )}
            </div>
          ) : activeRun.status === "cancelled" ? (
            <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              {activeRun.error_message ||
                "This research synthesis run was cancelled before completion."}
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
