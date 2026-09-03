"use client";

import { X } from "lucide-react";
import Image from "next/image";

import type { ImageAttachment } from "@/features/chat/types/attachments";

interface ImageAttachmentListProps {
  attachments: ImageAttachment[];
  onRemove: (id: string) => void;
  disabled?: boolean;
}

export function ImageAttachmentList({
  attachments,
  onRemove,
  disabled = false,
}: ImageAttachmentListProps) {
  if (attachments.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5 px-3 pt-3">
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {attachments.map((attachment, index) => (
          <div
            key={attachment.id}
            className="group relative size-16 shrink-0 overflow-hidden rounded-lg border border-border bg-secondary"
          >
            <Image
              src={attachment.previewUrl}
              alt={attachment.file.name || `Attachment ${index + 1}`}
              fill
              unoptimized
              className="object-cover"
            />

            <button
              type="button"
              disabled={disabled}
              onClick={() => onRemove(attachment.id)}
              aria-label={`Remove ${attachment.file.name || `image ${index + 1}`}`}
              title={`Remove ${attachment.file.name || `image ${index + 1}`}`}
              className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-background/80 text-foreground backdrop-blur-xs transition-colors hover:bg-destructive hover:text-destructive-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
            >
              <X className="size-3" />
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between px-0.5 text-[11px] text-muted-foreground">
        <span>{attachments.length} / 4 attached</span>
      </div>
    </div>
  );
}
