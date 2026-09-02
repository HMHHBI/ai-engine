"use client";

import { Check, FileText, LoaderCircle, X } from "lucide-react";

import type { PdfAttachment } from "@/features/chat/types/attachments";
import { cn } from "@/lib/utils";

interface PdfAttachmentProps {
  attachment: PdfAttachment;
  onRemove: () => void;
}

export function PdfAttachment({ attachment, onRemove }: PdfAttachmentProps) {
  const isUploading = attachment.status === "uploading";
  const isUploaded = attachment.status === "uploaded";
  const isError = attachment.status === "error";

  return (
    <div className="mx-3 mt-3 flex items-center gap-3 rounded-xl border border-border bg-secondary/50 px-3 py-2">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-background">
        <FileText className="size-4 text-muted-foreground" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{attachment.filename}</p>

        <p
          className={cn(
            "text-xs",
            isError ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {isUploading && "Uploading and processing…"}
          {isUploaded && `${attachment.chunksCount ?? 0} chunks indexed`}
          {isError && (attachment.error ?? "Upload failed.")}
          {attachment.status === "idle" && "Ready to upload"}
        </p>
      </div>

      {isUploading && (
        <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
      )}

      {isUploaded && <Check className="size-4 text-muted-foreground" />}

      <button
        type="button"
        onClick={onRemove}
        disabled={isUploading}
        aria-label="Remove PDF"
        className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
