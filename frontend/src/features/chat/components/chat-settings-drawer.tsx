"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import type { ChatPersona } from "@/types/api";

interface ChatSettingsDrawerProps {
  chatId: number;
  open: boolean;
  onClose: () => void;
}

const PERSONA_OPTIONS: Array<{
  value: ChatPersona;
  label: string;
  description: string;
}> = [
  {
    value: "default",
    label: "Default Assistant",
    description: "Balanced, general-purpose analysis across evidence.",
  },
  {
    value: "academic",
    label: "Academic Researcher",
    description: "Formal scholarly prose with disciplined citations.",
  },
  {
    value: "legal",
    label: "Legal Analyst",
    description: "Rigorous statutory precision and risk-aware breakdown.",
  },
  {
    value: "simple",
    label: "Simple Explainer",
    description: "Clear, concise breakdowns in plain English.",
  },
  {
    value: "developer",
    label: "Systems Architect",
    description: "Deep technical breakdowns, contracts, and architecture.",
  },
];

export function ChatSettingsDrawer({
  chatId,
  open,
  onClose,
}: ChatSettingsDrawerProps) {
  const session = useChatSessionStore((state) =>
    state.sessions.find((item) => item.id === chatId),
  );

  const [persona, setPersona] = useState<ChatPersona>(
    () => session?.persona ?? "default",
  );
  const [customInstructions, setCustomInstructions] = useState(
    () => session?.custom_instructions ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Single unified keyboard listener & focus trapping
  useEffect(() => {
    if (!open) return;

    const drawer = drawerRef.current;
    if (drawer) {
      const focusable = drawer.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length > 0) {
        focusable[0].focus();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!saving) {
          onClose();
        }
        return;
      }

      if (event.key === "Tab" && drawer) {
        const focusable = drawer.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose, saving]);

  if (!open) {
    return null;
  }

  async function handleSave() {
    setSaving(true);
    setError(null);

    try {
      await chatSessionActions.updatePersona(
        chatId,
        persona,
        customInstructions.trim(),
      );
      onClose();
    } catch {
      setError("Unable to save chat settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60]">
      <button
        type="button"
        aria-label="Close settings"
        className="absolute inset-0 bg-black/40 backdrop-blur-xs"
        onClick={() => {
          if (!saving) {
            onClose();
          }
        }}
      />

      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-settings-title"
        className="absolute bottom-0 right-0 top-0 flex w-full max-w-md flex-col border-l border-border bg-background shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2
              id="chat-settings-title"
              className="text-base font-semibold"
            >
              Research mode & persona
            </h2>
            <p className="text-xs text-muted-foreground">
              Customize reasoning tone and instructions for this session.
            </p>
          </div>

          <button
            type="button"
            aria-label="Close settings"
            disabled={saving}
            onClick={onClose}
            className="rounded-md p-2 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto p-5">
          <section className="space-y-3">
            <label className="text-sm font-medium">
              Research persona
            </label>

            <div className="space-y-2">
              {PERSONA_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                    persona === option.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:bg-secondary/50"
                  }`}
                >
                  <input
                    type="radio"
                    name="persona"
                    value={option.value}
                    checked={persona === option.value}
                    onChange={() => setPersona(option.value)}
                    className="mt-1"
                  />

                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {option.label}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {option.description}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <label
              htmlFor="custom-instructions"
              className="text-sm font-medium"
            >
              Custom instructions
            </label>

            <textarea
              id="custom-instructions"
              value={customInstructions}
              onChange={(event) =>
                setCustomInstructions(event.target.value)
              }
              placeholder="Tell the assistant how to behave or format responses..."
              rows={4}
              className="w-full rounded-lg border border-border bg-background p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </section>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border p-4">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            Cancel
          </button>

          <button
            type="button"
            disabled={saving}
            onClick={() => void handleSave()}
            className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
