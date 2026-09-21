"use client";

import { ChevronDown, FileText } from "lucide-react";
import { useId, useState } from "react";

import type { RetrievedSource } from "@/types/api";
import { cn } from "@/lib/utils";

interface CitationSourcesProps {
  sources?: RetrievedSource[];
  onCitationClick?: (source: RetrievedSource) => void;
}

function formatRelevance(distance: number): string {
  if (!Number.isFinite(distance)) {
    return "—";
  }

  const relevance = Math.max(0, Math.min(100, (1 - distance) * 100));

  return `${Math.round(relevance)}%`;
}

function formatPageNumber(pageNumber: number | null): string {
  return pageNumber === null ? "Page unavailable" : `Page ${pageNumber}`;
}

function formatChunkIndex(chunkIndex: number | null): string {
  return chunkIndex === null ? "Chunk unavailable" : `Chunk ${chunkIndex}`;
}

export function CitationSources({ sources, onCitationClick }: CitationSourcesProps) {
  const [isOpen, setIsOpen] = useState(false);
  const contentId = useId();

  if (!sources || sources.length === 0) {
    return null;
  }

  const sourceLabel = sources.length === 1 ? "Source" : "Sources";

  return (
    <div className="w-full max-w-full">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={contentId}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-2 py-1",
          "text-xs font-medium text-muted-foreground",
          "transition-colors hover:bg-secondary hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        <ChevronDown
          className={cn(
            "size-3.5 shrink-0 transition-transform",
            isOpen && "rotate-180",
          )}
          aria-hidden="true"
        />

        <FileText className="size-3.5 shrink-0" aria-hidden="true" />

        <span>
          {sources.length} {sourceLabel}
        </span>
      </button>

      <div
        id={contentId}
        hidden={!isOpen}
        className={cn("mt-2 w-full space-y-2", !isOpen && "hidden")}
      >
        <div
          className="space-y-2"
          aria-label={`${sources.length} ${sourceLabel.toLowerCase()}`}
        >
          {sources.map((source, index) => {
            const canNavigate =
              source.document_id !== null &&
              source.document_id !== undefined &&
              source.page_number !== null;

            return (
              <div
                key={`${source.id}-${source.chunk_index ?? "unknown"}-${index}`}
                onClick={() => {
                  if (canNavigate) {
                    onCitationClick?.(source);
                  }
                }}
                className={cn(
                  "rounded-lg border border-border bg-card/70",
                  "px-3 py-2.5 text-xs sm:px-3.5 sm:py-3",
                  canNavigate &&
                    "cursor-pointer transition-colors hover:bg-secondary/70 hover:border-primary/40",
                  !canNavigate && "cursor-default",
                )}
                data-testid={`citation-source-${source.id}`}
              >
                <div className="flex min-w-0 items-start gap-2">
                  <div
                    className={cn(
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center",
                      "rounded-md bg-secondary text-muted-foreground",
                    )}
                    aria-hidden="true"
                  >
                    <FileText className="size-3.5" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate font-medium text-foreground">
                        Source {index + 1}
                      </span>

                      <span className="shrink-0 text-muted-foreground">
                        Relevance {formatRelevance(source.distance)}
                      </span>
                    </div>

                    <div className="mt-1 flex min-w-0 flex-wrap gap-x-2 gap-y-1 text-muted-foreground">
                      <span data-testid="citation-page">
                        {formatPageNumber(source.page_number)}
                      </span>

                      <span aria-hidden="true">·</span>

                      <span>{formatChunkIndex(source.chunk_index)}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
