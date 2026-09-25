"use client";

import {
  ChevronDown,
  ExternalLink,
  FileText,
  Quote,
} from "lucide-react";
import { useId, useState } from "react";

import { useDocumentStore } from "@/features/documents/document-store";
import { cn } from "@/lib/utils";
import type { RetrievedSource } from "@/types/api";

interface CitationSourcesProps {
  sources?: RetrievedSource[];
  onCitationClick?: (source: RetrievedSource) => void;
}

function formatRelevance(distance: number): string {
  if (!Number.isFinite(distance)) {
    return "—";
  }

  const relevance = Math.max(
    0,
    Math.min(100, (1 - distance) * 100),
  );

  return `${Math.round(relevance)}%`;
}

function formatPageNumber(pageNumber: number | null): string {
  return pageNumber === null ? "Page unavailable" : `Page ${pageNumber}`;
}

function formatChunkIndex(chunkIndex: number | null): string {
  return chunkIndex === null
    ? "Chunk unavailable"
    : `Chunk ${chunkIndex}`;
}

function getSourceQuote(source: RetrievedSource): string | null {
  const snippet = source.snippet?.trim();

  return snippet ? snippet : null;
}

export function CitationSources({
  sources,
  onCitationClick,
}: CitationSourcesProps) {
  const [isOpen, setIsOpen] = useState(false);
  const contentId = useId();

  const documentsByChat = useDocumentStore(
    (state) => state.documentsByChat,
  );

  if (!sources || sources.length === 0) {
    return null;
  }

  const documentIndex = new Map(
    Object.values(documentsByChat)
      .flat()
      .map((document) => [document.id, document]),
  );

  const sourceLabel = sources.length === 1 ? "source" : "sources";

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

        <FileText
          className="size-3.5 shrink-0"
          aria-hidden="true"
        />

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
          aria-label={`${sources.length} ${sourceLabel}`}
        >
          {sources.map((source, index) => {
            const document =
              source.document_id !== null &&
              source.document_id !== undefined
                ? documentIndex.get(source.document_id)
                : undefined;

            const documentTitle =
              document?.filename ?? "Research document";

            const canNavigate =
              source.document_id !== null &&
              source.document_id !== undefined &&
              source.page_number !== null;

            const quote = getSourceQuote(source);
            const relevanceFormatted = formatRelevance(source.distance);

            return (
              <article
                key={`${source.id}-${source.chunk_index ?? "unknown"}-${index}`}
                data-testid={`citation-source-${source.id}`}
                className="rounded-xl border border-border bg-card px-3.5 py-3.5 sm:px-4"
              >
                <div className="flex items-start gap-3">
                  <div
                    className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary"
                    aria-hidden="true"
                  >
                    {index + 1}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-start justify-between gap-3">
                      <div className="min-w-0">
                        <span className="sr-only">Source {index + 1}</span>

                        <p
                          className="truncate text-sm font-semibold text-foreground"
                          title={documentTitle}
                        >
                          [{index + 1}] {documentTitle}
                        </p>

                        <p
                          data-testid="citation-page"
                          className="mt-1 text-xs text-muted-foreground"
                        >
                          {formatPageNumber(source.page_number)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 rounded-lg bg-muted/40 px-3 py-2.5">
                      <div className="flex items-start gap-2">
                        <Quote
                          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
                          aria-hidden="true"
                        />

                        {quote ? (
                          <blockquote
                            data-testid="citation-snippet"
                            className="text-xs leading-5 text-foreground"
                          >
                            “{quote}”
                          </blockquote>
                        ) : (
                          <p
                            data-testid="citation-evidence-location"
                            className="text-xs leading-5 text-muted-foreground"
                          >
                            Evidence is available on{" "}
                            {formatPageNumber(source.page_number)}.
                            Open the document to inspect the cited passage.
                          </p>
                        )}
                      </div>
                    </div>

                    {canNavigate ? (
                      <button
                        type="button"
                        onClick={() => onCitationClick?.(source)}
                        className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <span>Open in Document</span>
                        <ExternalLink
                          className="size-3.5"
                          aria-hidden="true"
                        />
                      </button>
                    ) : (
                      <span className="mt-3 inline-flex text-xs text-muted-foreground">
                        Document navigation unavailable
                      </span>
                    )}

                    <details
                      data-testid={`citation-details-${source.id}`}
                      className="mt-3 rounded-lg border border-border/70 bg-background"
                    >
                      <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        Technical details
                      </summary>

                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border/70 px-3 py-2 text-[11px] text-muted-foreground">
                        <span className="sr-only">
                          Relevance {relevanceFormatted}
                        </span>

                        <span>Relevance</span>
                        <span className="text-right text-foreground">
                          {relevanceFormatted}
                        </span>

                        <span>Chunk</span>
                        <span
                          data-testid="citation-chunk"
                          className="text-right text-foreground"
                        >
                          {formatChunkIndex(source.chunk_index)}
                        </span>

                        <span>Source ID</span>
                        <span className="text-right text-foreground">
                          {source.id}
                        </span>
                      </div>
                    </details>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
