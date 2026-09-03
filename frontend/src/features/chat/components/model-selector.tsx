"use client";

import { ChevronDown, Cpu } from "lucide-react";

import type { AIModel, AIProvider } from "@/types/api";
import { cn } from "@/lib/utils";

interface ModelOption {
  provider: AIProvider;
  model: AIModel;
  label: string;
}

const MODEL_OPTIONS: ModelOption[] = [
  {
    provider: "ollama",
    model: "llama3.2",
    label: "Llama 3.2",
  },
  {
    provider: "ollama",
    model: "deepseek-r1",
    label: "DeepSeek R1",
  },
  {
    provider: "gemini",
    model: "gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
  },
  {
    provider: "openai",
    model: "gpt-4o-mini",
    label: "GPT-4o Mini",
  },
];

interface ModelSelectorProps {
  model: AIModel;
  provider: AIProvider;
  onChange: (model: AIModel, provider: AIProvider) => void;
  disabled?: boolean;
}

export function ModelSelector({
  model,
  provider,
  onChange,
  disabled = false,
}: ModelSelectorProps) {
  const selectedValue = `${provider}:${model}`;

  function handleChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const selected = MODEL_OPTIONS.find(
      (option) => `${option.provider}:${option.model}` === event.target.value,
    );

    if (!selected) {
      return;
    }

    onChange(selected.model, selected.provider);
  }

  return (
    <div className="relative">
      <Cpu
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
      />

      <select
        value={selectedValue}
        onChange={handleChange}
        disabled={disabled}
        aria-label="AI model"
        className={cn(
          "h-8 appearance-none rounded-lg border border-border",
          "bg-background pl-8 pr-7 text-xs font-medium",
          "text-foreground outline-none",
          "transition-colors hover:bg-secondary",
          "focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        {MODEL_OPTIONS.map(
          ({ provider: optionProvider, model: optionModel, label }) => (
            <option
              key={`${optionProvider}:${optionModel}`}
              value={`${optionProvider}:${optionModel}`}
            >
              {label}
            </option>
          ),
        )}
      </select>

      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}
