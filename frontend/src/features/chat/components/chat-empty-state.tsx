import { Sparkles } from "lucide-react";

export function ChatEmptyState() {
  return (
    <div className="flex flex-1 items-center justify-center px-6">
      <div className="w-full max-w-xl text-center">
        <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-xl border border-border bg-card">
          <Sparkles className="size-5 text-muted-foreground" />
        </div>

        <h2 className="text-2xl font-semibold tracking-tight">
          How can I help you?
        </h2>

        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
          Ask a question, analyze a document, or start a new conversation.
        </p>
      </div>
    </div>
  );
}
