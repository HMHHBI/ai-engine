import { LoaderCircle } from "lucide-react";

export function StreamingIndicator() {
  return (
    <div className="mx-auto flex w-full max-w-3xl items-center gap-3 px-4 py-2">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-card">
        <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
      </div>

      <span className="text-sm text-muted-foreground">Thinking…</span>
    </div>
  );
}
