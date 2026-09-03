import { AlertCircle } from "lucide-react";
import { RetryButton } from "@/components/feedback/retry-button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  retrying?: boolean;
  className?: string;
}

export function ErrorState({
  title = "Error",
  message,
  actionLabel = "Try again",
  onAction,
  retrying = false,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center p-6 text-center",
        className,
      )}
    >
      <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertCircle className="size-5" />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{message}</p>
      {onAction && (
        <div className="mt-4">
          <RetryButton
            retrying={retrying}
            label={actionLabel}
            onClick={onAction}
          />
        </div>
      )}
    </div>
  );
}
