"use client";

import { X } from "lucide-react";
import Image from "next/image";

import type { ImageAttachment } from "@/features/chat/types/attachments";
import { IconButton } from "@/components/ui/icon-button";

interface ImageAttachmentListProps {
  attachments: ImageAttachment[];
  onRemove: (id: string) => void;
}

export function ImageAttachmentList({
  attachments,
  onRemove,
}: ImageAttachmentListProps) {
  if (attachments.length === 0) {
    return null;
  }

  return (
    <div className="flex gap-2 overflow-x-auto px-3 pt-3">
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="relative size-16 shrink-0 overflow-hidden rounded-lg border border-border bg-secondary"
        >
          <Image
            src={attachment.previewUrl}
            alt={attachment.file.name}
            fill
            unoptimized
            className="object-cover"
          />

          <IconButton
            label={`Remove ${attachment.file.name}`}
            onClick={() => onRemove(attachment.id)}
            className="absolute right-1 top-1 size-6 bg-background/80 text-foreground backdrop-blur-sm hover:bg-background"
          >
            <X className="size-3" />
          </IconButton>
        </div>
      ))}
    </div>
  );
}
