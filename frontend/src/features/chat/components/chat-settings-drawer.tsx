"use client";

import { useEffect, useState, useRef } from "react";
import { X } from "lucide-react";

import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import type { ChatPersona } from "@/types/api";

interface ChatSettingsDrawerProps {
  chatId: number;
  open: boolean;
  onClose: () => void;
}

const PERSONAS: Array<{
  value: ChatPersona;
  label: string;
  description: string;
}> = [
  {
    value: "default",
    label: "Default",
    description: "Balanced and professional responses.",
  },
  {
    value: "academic",
    label: "Academic",
    description: "Rigorous, analytical, scholarly responses.",
  },
  {
    value: "developer",
    label: "Developer",
    description: "Concise engineering-focused responses.",
  },
  {
    value: "legal",
    label: "Legal",
    description: "Precise wording, conditions, and exceptions.",
  },
  {
    value: "simple",
    label: "Simple",
    description: "Plain-language explanations.",
  },
];

const MAX_INSTRUCTIONS = 2000;

export function ChatSettingsDrawer({
  chatId,
  open,
  onClose,
}: ChatSettingsDrawerProps) {
  const session = useChatSessionStore((state) =>
    state.sessions.find((item) => item.id === chatId),
  );

  const [persona, setPersona] = useState<ChatPersona>(() => session?.persona ?? "default");
  const [customInstructions, setCustomInstructions] = useState(() => session?.custom_instructions ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Focus management: initial focus and focus trap
  useEffect(() => {
    if (!open) return;

    const drawer = drawerRef.current;
    if (!drawer) return;

    const focusable = drawer.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length > 0) {
      focusable[0].focus();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!saving) {
          onClose();
        }
        return;
      }

      if (event.key === "Tab") {
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

    document.addEventListener("keydown", handleGlobalKeyDown);
    return () => {
      document.removeEventListener("keydown", handleGlobalKeyDown);
    };

    function handleGlobalKeyDown(event: KeyboardEvent) {
      handleKeyDown(event);
    }
  }, [open, onClose, saving]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !saving) {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose, saving]);

  async function handleSave() {
    if (!session) {
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await chatSessionActions.updatePersona(
        chatId,
        persona,
        customInstructions,
      );

      onClose();
    } catch {
      setError("Unable to save chat settings.");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50" role="presentation">
      <button
        type="button"
        aria-label="Close chat settings"
        className="absolute inset-0 bg-black/40 backdrop-blur-xs"
        onClick={() => {
          if (!saving) {
            onClose();
          }
        }}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-settings-title"
        className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l border-border bg-background shadow-xl"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div>
            <h2
              id="chat-settings-title"
              className="text-sm font-semibold"
            >
              Research settings
            </h2>

            <p className="text-xs text-muted-foreground">
              Customize how this research session responds.
            </p>
          </div>

          <button
            type="button"
            aria-label="Close chat settings"
            disabled={saving}
            onClick={onClose}
            className="rounded-md p-2 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {!session ? (
            <p className="text-sm text-muted-foreground">
              Research session is still loading.
            </p>
          ) : (
            <div className="space-y-6">
              <fieldset>
                <legend className="text-sm font-medium">
                  Research mode
                </legend>

                <div className="mt-3 space-y-2">
                  {PERSONAS.map((item) => (
                    <label
                      key={item.value}
                      className="flex cursor-pointer gap-3 rounded-lg border border-border p-3 hover:bg-secondary/50"
                    >
                      <input
                        type="radio"
                        name={`chat-persona-${chatId}`}
                        value={item.value}
                        checked={persona === item.value}
                        onChange={() => setPersona(item.value)}
                        disabled={saving}
                        className="mt-0.5"
                      />

                      <span className="min-w-0">
                        <span className="block text-sm font-medium">
                          {item.label}
                        </span>

                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {item.description}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div>
                <div className="flex items-center justify-between">
                  <label
                    htmlFor={`chat-custom-instructions-${chatId}`}
                    className="text-sm font-medium"
                  >
                    Custom instructions
                  </label>

                  <span className="text-xs text-muted-foreground">
                    {customInstructions.length}/{MAX_INSTRUCTIONS}
                  </span>
                </div>

                <textarea
                  id={`chat-custom-instructions-${chatId}`}
                  value={customInstructions}
                  maxLength={MAX_INSTRUCTIONS}
                  disabled={saving}
                  onChange={(event) =>
                    setCustomInstructions(event.target.value)
                  }
                  placeholder="Tell the assistant how you want this research session to behave..."
                  className="mt-2 min-h-32 w-full resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
              </div>

              {error && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                >
                  {error}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-border p-4">
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
            disabled={!session || saving}
            onClick={() => void handleSave()}
            className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </aside>
    </div>
  );
}
