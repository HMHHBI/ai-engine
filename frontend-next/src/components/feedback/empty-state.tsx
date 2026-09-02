import { MessageSquarePlus } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  actionLoading?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  actionLoading = false,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center p-6 text-center",
        className,
      )}
    >
      <div className="mb-3 flex size-10 items-center justify-center rounded-xl border border-border bg-secondary text-muted-foreground">
        {icon ?? <MessageSquarePlus className="size-5" />}
      </div>
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">
        {description}
      </p>
      {actionLabel && onAction && (
        <button
          type="button"
          disabled={actionLoading}
          onClick={onAction}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-xs transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-50"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
