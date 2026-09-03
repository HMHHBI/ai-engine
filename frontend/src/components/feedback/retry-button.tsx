"use client";

import { LoaderCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface RetryButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  retrying?: boolean;
  label?: string;
}

export function RetryButton({
  retrying = false,
  label = "Try again",
  className,
  disabled,
  ...props
}: RetryButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || retrying}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-xs transition-colors hover:bg-secondary disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {retrying ? (
        <LoaderCircle className="size-3.5 animate-spin" />
      ) : (
        <RefreshCw className="size-3.5" />
      )}
      <span>{retrying ? "Retrying..." : label}</span>
    </button>
  );
}
