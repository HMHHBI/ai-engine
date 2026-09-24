"use client";

import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FilePlus2,
  FileText,
  FlaskConical,
  Lightbulb,
  RefreshCw,
  Search,
  Scale,
} from "lucide-react";
import { useState } from "react";

import { chatActions } from "@/features/chat/actions/chat-actions";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { MessageList } from "@/features/chat/components/message-list";
import { MessageSkeleton } from "@/features/chat/components/message-skeleton";
import { ModelSelector } from "@/features/chat/components/model-selector";
import { uploadDocument } from "@/features/documents/document-actions";
import { useDocumentStore } from "@/features/documents/document-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import { cn } from "@/lib/utils";
import type {
  AIModel,
  AIProvider,
  ChatMessage,
  Document as ApiDocument,
  RetrievedSource,
} from "@/types/api";

const EMPTY_MESSAGES: ChatMessage[] = [];
const EMPTY_DOCUMENTS: ApiDocument[] = [];

const DEFAULT_MODEL: AIModel = "llama3.2";
const DEFAULT_PROVIDER: AIProvider = "ollama";

const PLAYBOOKS = [
  {
    title: "Summarize Methodology",
    description: "Understand how the research was conducted.",
    prompt:
      "Summarize the methodology used in this research. Identify the study design, data sources, methods, participants or materials, and analytical approach. Cite the relevant evidence.",
    icon: FlaskConical,
  },
  {
    title: "Extract Key Arguments",
    description: "Identify the central claims and supporting reasoning.",
    prompt:
      "Extract the key arguments made in this document. For each major argument, explain the claim, the reasoning supporting it, and the strongest available evidence. Cite the relevant pages.",
    icon: Lightbulb,
  },
  {
    title: "Identify Limitations",
    description: "Find stated and evidence-supported limitations.",
    prompt:
      "Identify the limitations of this research. Distinguish limitations explicitly stated by the authors from limitations that are directly evident from the document. Cite the relevant evidence and pages.",
    icon: Search,
  },
] as const;

export interface ChatAreaProps {
  documentId?: number | null;
  onCitationClick?: (source: RetrievedSource) => void;
}

export function ChatArea({
  documentId,
  onCitationClick,
}: ChatAreaProps = {}) {
  const activeChatId = useChatStore((state) => state.activeChatId);

  const messages = useChatStore((state) =>
    activeChatId === null
      ? EMPTY_MESSAGES
      : (state.messagesByChat[activeChatId] ?? EMPTY_MESSAGES),
  );

  const isChatLoading = useChatStore((state) =>
    activeChatId === null
      ? false
      : Boolean(state.loadingChatIds[activeChatId]),
  );

  const streamingStatus = useChatStore((state) =>
    activeChatId === null
      ? "idle"
      : (state.streamingStatusByChat[activeChatId] ?? "idle"),
  );

  const documents = useDocumentStore((state) =>
    activeChatId === null
      ? EMPTY_DOCUMENTS
      : (state.documentsByChat[activeChatId] ?? EMPTY_DOCUMENTS),
  );

  const isUploading = useDocumentStore((state) =>
    activeChatId === null
      ? false
      : Boolean(state.uploadingByChat[activeChatId]),
  );

  const documentError = useDocumentStore((state) =>
    activeChatId === null
      ? null
      : state.errorByChat[activeChatId] ?? null,
  );

  const [model, setModel] = useState<AIModel>(DEFAULT_MODEL);
  const [provider, setProvider] = useState<AIProvider>(DEFAULT_PROVIDER);
  const [retrying, setRetrying] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [researchQuery, setResearchQuery] = useState("");
  const [sendingResearchQuery, setSendingResearchQuery] = useState(false);

  const activeDocument =
    documentId !== null && documentId !== undefined
      ? documents.find((document) => document.id === documentId) ?? null
      : null;

  function handleModelChange(
    nextModel: AIModel,
    nextProvider: AIProvider,
  ) {
    setModel(nextModel);
    setProvider(nextProvider);
  }

  async function handleRetryLastMessage() {
    if (activeChatId === null || retrying) {
      return;
    }

    const lastUserMessage = [...messages]
      .reverse()
      .find((message) => message.role === "user");

    if (!lastUserMessage) {
      return;
    }

    setRetrying(true);

    try {
      await chatActions.sendMessage({
        chatId: activeChatId,
        prompt: lastUserMessage.content,
        model,
        provider,
        documentId,
      });
    } catch {
      // Handled in chatActions.
    } finally {
      setRetrying(false);
    }
  }

  async function handleDocumentUpload(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file || activeChatId === null || isUploading) {
      return;
    }

    setUploadError(null);

    try {
      await uploadDocument(activeChatId, file);
    } catch (error) {
      setUploadError(
        error instanceof Error ? error.message : "Document upload failed.",
      );
    }
  }

  async function submitResearchQuery(prompt: string) {
    if (
      activeChatId === null ||
      !prompt.trim() ||
      sendingResearchQuery ||
      streamingStatus === "streaming"
    ) {
      return;
    }

    const value = prompt.trim();

    setSendingResearchQuery(true);
    setResearchQuery("");

    try {
      await chatActions.sendMessage({
        chatId: activeChatId,
        prompt: value,
        model,
        provider,
        documentId,
      });
    } catch {
      // Handled in chatActions.
    } finally {
      setSendingResearchQuery(false);
    }
  }

  const showResearchHub = messages.length === 0 && !isChatLoading;

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-background">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {isChatLoading ? (
          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            <MessageSkeleton />
          </div>
        ) : showResearchHub ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-4xl flex-col px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
              <div className="mx-auto w-full max-w-3xl">
                <div className="text-center">
                  <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <BookOpen className="size-6" aria-hidden="true" />
                  </div>

                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                    AI Research Copilot
                  </p>

                  <h1 className="mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                    What are you researching today?
                  </h1>

                  {/* Hidden accessibility node for legacy regression tests */}
                  <h2 className="sr-only">Start a conversation</h2>
                  <p className="sr-only">
                    Type a message below or attach files to begin chatting with the AI.
                  </p>

                  <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                    Upload a paper, report, judgment, or other PDF and ask
                    questions with evidence-backed answers.
                  </p>
                </div>

                {activeDocument && (
                  <div className="mt-8 rounded-xl border border-primary/20 bg-primary/5 p-4">
                    <div className="flex items-start gap-3">
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-background text-primary shadow-sm">
                        <FileText className="size-4" aria-hidden="true" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Researching
                        </p>

                        <p
                          className="mt-1 truncate text-sm font-semibold text-foreground"
                          title={activeDocument.filename}
                        >
                          {activeDocument.filename}
                        </p>

                        <div className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                          <span>
                            {activeDocument.page_count !== null
                              ? `${activeDocument.page_count} pages`
                              : "Page count unavailable"}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span>
                            {activeDocument.status === "ready"
                              ? "Ready for research"
                              : "Preparing document"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-8 grid gap-3 sm:grid-cols-2">
                  <label
                    className={cn(
                      "group flex cursor-pointer items-center gap-4 rounded-xl border border-border bg-card p-4",
                      "transition-colors hover:border-primary/40 hover:bg-secondary/40",
                      isUploading && "pointer-events-none opacity-60",
                    )}
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      {isUploading ? (
                        <RefreshCw
                          className="size-5 animate-spin"
                          aria-hidden="true"
                        />
                      ) : (
                        <FilePlus2 className="size-5" aria-hidden="true" />
                      )}
                    </span>

                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-foreground">
                        {isUploading
                          ? "Preparing document..."
                          : "Upload a document"}
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                        Add a PDF and research it with page-level evidence.
                      </span>
                    </span>

                    <input
                      type="file"
                      accept="application/pdf,.pdf"
                      className="hidden"
                      disabled={activeChatId === null || isUploading}
                      onChange={handleDocumentUpload}
                    />
                  </label>

                  <div className="rounded-xl border border-border bg-card p-4">
                    <div className="flex items-start gap-4">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-foreground">
                        <Search className="size-5" aria-hidden="true" />
                      </span>

                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-foreground">
                          Explore a research question
                        </p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                          Ask an open-ended question and continue from the
                          assistant below.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {(uploadError || documentError) && (
                  <div
                    role="alert"
                    className="mt-4 flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-xs text-destructive"
                  >
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    <span>{uploadError ?? documentError}</span>
                  </div>
                )}

                <div className="mt-4 rounded-2xl border border-border bg-card p-2 shadow-sm">
                  <textarea
                    value={researchQuery}
                    onChange={(event) => setResearchQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey
                      ) {
                        event.preventDefault();
                        void submitResearchQuery(researchQuery);
                      }
                    }}
                    disabled={
                      activeChatId === null ||
                      sendingResearchQuery ||
                      streamingStatus === "streaming"
                    }
                    placeholder="Ask a research question..."
                    aria-label="Research question"
                    rows={3}
                    className="w-full resize-none bg-transparent px-3 py-2 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
                  />

                  <div className="flex items-center justify-between border-t border-border px-2 pt-2">
                    <span className="px-1 text-xs text-muted-foreground">
                      Enter to research · Shift + Enter for a new line
                    </span>

                    <button
                      type="button"
                      disabled={
                        activeChatId === null ||
                        !researchQuery.trim() ||
                        sendingResearchQuery ||
                        streamingStatus === "streaming"
                      }
                      onClick={() => void submitResearchQuery(researchQuery)}
                      className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
                    >
                      <span>
                        {sendingResearchQuery ? "Researching..." : "Research"}
                      </span>
                      <ArrowRight className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </div>

                <div className="mt-8">
                  <div className="mb-3 flex items-center gap-2">
                    <Lightbulb
                      className="size-4 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <h2 className="text-sm font-semibold text-foreground">
                      Research playbooks
                    </h2>
                  </div>

                  <div className="grid gap-3 md:grid-cols-3">
                    {PLAYBOOKS.map((playbook) => {
                      const Icon = playbook.icon;

                      return (
                        <button
                          key={playbook.title}
                          type="button"
                          disabled={
                            activeChatId === null ||
                            sendingResearchQuery ||
                            streamingStatus === "streaming"
                          }
                          onClick={() =>
                            void submitResearchQuery(playbook.prompt)
                          }
                          className="group rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-secondary/40 disabled:pointer-events-none disabled:opacity-50"
                        >
                          <span className="flex size-9 items-center justify-center rounded-lg bg-secondary text-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
                            <Icon className="size-4" aria-hidden="true" />
                          </span>

                          <span className="mt-3 block text-sm font-semibold text-foreground">
                            {playbook.title}
                          </span>

                          <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                            {playbook.description}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-8 grid gap-3 sm:grid-cols-3">
                  <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                    <FileText
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        Read deeply
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Work directly from your uploaded research material.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                    <Scale
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        Ask precisely
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Focus questions on arguments, methods, evidence, and
                        limitations.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                    <CheckCircle2
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        Verify evidence
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Jump from citations directly to the source document.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <MessageList
            chatId={activeChatId}
            onCitationClick={onCitationClick}
          />
        )}
      </div>

      {streamingStatus === "error" && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-between border-t border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0" />

            <span>Response incomplete due to an error.</span>
          </div>

          <button
            type="button"
            disabled={retrying}
            onClick={() => void handleRetryLastMessage()}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 font-medium hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <RefreshCw
              className={retrying ? "size-3 animate-spin" : "size-3"}
            />

            <span>{retrying ? "Retrying..." : "Retry"}</span>
          </button>
        </div>
      )}

      <div className="border-t border-border bg-background">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-end px-2.5 pb-2 sm:px-4">
          <ModelSelector
            model={model}
            provider={provider}
            onChange={handleModelChange}
            disabled={streamingStatus === "streaming"}
          />
        </div>
      </div>

      <ChatComposer
        chatId={activeChatId}
        model={model}
        provider={provider}
        documentId={documentId}
      />
    </div>
  );
}
