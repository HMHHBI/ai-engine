"use client";

import { forwardRef, useRef, useState } from "react";
import { ChevronDown, FileText, Menu, PanelLeft, Settings, Sparkles } from "lucide-react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

import { IconButton } from "@/components/ui/icon-button";
import { RagStatusBadge } from "@/features/chat/components/rag-status-badge";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { ChatSettingsDrawer } from "@/features/chat/components/chat-settings-drawer";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { DocumentWorkspace } from "@/features/documents/components/DocumentWorkspace";
import type { ChatPersona } from "@/types/api";

interface AppHeaderProps {
  onOpenMobileSidebar: () => void;
  onToggleSidebar: () => void;
}

const PERSONA_LABELS: Record<ChatPersona, string> = {
  default: "Default",
  academic: "Academic",
  developer: "Developer",
  legal: "Legal",
  simple: "Simple",
};

const PERSONAS: ChatPersona[] = [
  "default",
  "academic",
  "developer",
  "legal",
  "simple",
];

export const AppHeader = forwardRef<HTMLButtonElement, AppHeaderProps>(
  function AppHeader({ onOpenMobileSidebar, onToggleSidebar }, ref) {
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();

    const isResearchView = searchParams?.get("view") === "research";

    const [settingsOpen, setSettingsOpen] = useState(false);
    const settingsTriggerRef = useRef<HTMLButtonElement>(null);
    const [documentsOpen, setDocumentsOpen] = useState(false);
    const [personaOpen, setPersonaOpen] = useState(false);
    const [personaSaving, setPersonaSaving] = useState(false);
    const [personaError, setPersonaError] = useState<string | null>(null);
    const docTriggerRef = useRef<HTMLButtonElement>(null);

    const activeChatId = useChatStore((state) => state.activeChatId);

    const activeSession = useChatSessionStore((state) =>
      activeChatId === null
        ? null
        : state.sessions.find((item) => item.id === activeChatId),
    );

    const title = isResearchView
      ? "Research Synthesis"
      : (activeSession?.title ?? "AI Engine");
    const persona = activeSession?.persona ?? "default";

    function toggleResearchView() {
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      if (isResearchView) {
        params.delete("view");
      } else {
        params.set("view", "research");
      }
      const query = params.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    }

    async function handlePersonaChange(nextPersona: ChatPersona) {
      if (
        activeChatId === null ||
        !activeSession ||
        personaSaving ||
        nextPersona === persona
      ) {
        return;
      }

      setPersonaSaving(true);
      setPersonaError(null);

      try {
        await chatSessionActions.updatePersona(
          activeChatId,
          nextPersona,
          activeSession.custom_instructions ?? "",
        );

        setPersonaOpen(false);
      } catch {
        setPersonaError("Unable to update research mode.");
      } finally {
        setPersonaSaving(false);
      }
    }

    return (
      <>
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border/70 bg-background/80 backdrop-blur-md px-2 sm:px-3">
          <div className="flex min-w-0 flex-1 items-center gap-1.5 sm:gap-2">
            <div className="md:hidden">
              <IconButton
                ref={ref}
                label="Open sidebar"
                onClick={onOpenMobileSidebar}
                className="size-9"
              >
                <Menu className="size-5" />
              </IconButton>
            </div>

            <div className="hidden md:block">
              <IconButton
                label="Toggle sidebar"
                onClick={onToggleSidebar}
                className="size-9"
              >
                <PanelLeft className="size-4" />
              </IconButton>
            </div>

            <div className="min-w-0 flex-1">
              <h1 className="truncate text-xs font-medium sm:text-sm">
                {title}
              </h1>
            </div>
          </div>

          <div className="ml-1.5 flex shrink-0 items-center gap-1 sm:ml-2">
            {/* Quick Toggle for Cross-Document Synthesis Workbench */}
            <IconButton
              label={isResearchView ? "Exit research synthesis" : "Open research synthesis"}
              onClick={toggleResearchView}
              className={`size-9 ${isResearchView ? "text-primary bg-primary/10" : ""}`}
              data-testid="toggle-research-synthesis-button"
            >
              <Sparkles className="size-4" />
            </IconButton>

            {activeChatId !== null && activeSession && !isResearchView && (
              <div className="relative">
                <button
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={personaOpen}
                  disabled={personaSaving}
                  onClick={() => {
                    setPersonaOpen((open) => !open);
                    setPersonaError(null);
                  }}
                  className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 sm:text-sm"
                  data-testid="research-mode-selector"
                >
                  <span>{PERSONA_LABELS[persona]}</span>
                  <ChevronDown className="size-3.5" />
                </button>

                {personaOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 top-full z-40 mt-2 w-44 rounded-xl border border-border/80 bg-background/95 p-1 shadow-xl backdrop-blur-md ring-1 ring-black/5 dark:ring-white/5"
                  >
                    {PERSONAS.map((item) => (
                      <button
                        key={item}
                        type="button"
                        role="menuitem"
                        disabled={personaSaving}
                        aria-current={item === persona ? "true" : undefined}
                        onClick={() => void handlePersonaChange(item)}
                        className="flex w-full items-center rounded-md px-3 py-2 text-left text-sm hover:bg-secondary disabled:opacity-50"
                      >
                        {PERSONA_LABELS[item]}
                      </button>
                    ))}

                    {personaError && (
                      <p
                        role="alert"
                        className="px-3 py-2 text-xs text-destructive"
                      >
                        {personaError}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {!isResearchView && <RagStatusBadge chatId={activeChatId} />}

            {activeChatId !== null && !isResearchView && (
              <>
                <IconButton
                  ref={docTriggerRef}
                  label="Documents workspace"
                  onClick={() => setDocumentsOpen(true)}
                  className="size-9"
                  data-testid="open-documents-button"
                >
                  <FileText className="size-4" />
                </IconButton>

                <IconButton
                  label="Chat settings"
                  ref={settingsTriggerRef}
                  onClick={() => setSettingsOpen(true)}
                  className="size-9"
                >
                  <Settings className="size-4" />
                </IconButton>
              </>
            )}
          </div>
        </header>

        {activeChatId !== null && (
          <>
            {settingsOpen && (
              <ChatSettingsDrawer
                chatId={activeChatId}
                open
                onClose={() => {
                  setSettingsOpen(false);
                  settingsTriggerRef.current?.focus();
                }}
              />
            )}

            <DocumentWorkspace
              chatId={activeChatId}
              isOpen={documentsOpen}
              onClose={() => setDocumentsOpen(false)}
              triggerRef={docTriggerRef}
            />
          </>
        )}
      </>
    );
  },
);
