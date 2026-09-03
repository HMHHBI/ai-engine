"use client";

import {
  ArrowUp,
  FilePlus2,
  ImagePlus,
  LoaderCircle,
  Square,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { chatActions } from "@/features/chat/actions/chat-actions";
import { ImageAttachmentList } from "@/features/chat/components/image-attachment-list";
import { PdfAttachment as PdfAttachmentView } from "@/features/chat/components/pdf-attachment";
import { useChatStore } from "@/features/chat/store/chat-store";
import type {
  ImageAttachment,
  PdfAttachment,
} from "@/features/chat/types/attachments";
import {
  fileToBase64,
  validateImage,
  validatePdf,
} from "@/features/chat/utils/attachment-utils";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  chatId: number | null;
}

const TEXTAREA_MAX_HEIGHT = 220;

export function ChatComposer({ chatId }: ChatComposerProps) {
  const [prompt, setPrompt] = useState("");
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [pdf, setPdf] = useState<PdfAttachment | null>(null);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const pdfInputRef = useRef<HTMLInputElement | null>(null);
  const imagesRef = useRef<ImageAttachment[]>([]);

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  // Clean up object URLs on chat change or component unmount
  useEffect(() => {
    return () => {
      for (const image of imagesRef.current) {
        URL.revokeObjectURL(image.previewUrl);
      }
    };
  }, [chatId]);

  const status = useChatStore((state) =>
    chatId === null ? "idle" : (state.streamingStatusByChat[chatId] ?? "idle"),
  );

  const isStreaming = status === "streaming";
  const isUploadingOrProcessing =
    pdf?.status === "uploading" || pdf?.status === "processing";

  const canSend =
    chatId !== null &&
    prompt.trim().length > 0 &&
    !isStreaming &&
    !isUploadingOrProcessing;

  useEffect(() => {
    const textarea = textareaRef.current;

    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";

    const nextHeight = Math.min(textarea.scrollHeight, TEXTAREA_MAX_HEIGHT);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > TEXTAREA_MAX_HEIGHT ? "auto" : "hidden";
  }, [prompt]);

  function clearAttachmentError() {
    setAttachmentError(null);
  }

  async function handleImageSelection(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    clearAttachmentError();

    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    const remainingSlots = 4 - images.length;

    if (remainingSlots <= 0) {
      setAttachmentError("You can attach up to 4 images.");
      return;
    }

    const selectedFiles = files.slice(0, remainingSlots);
    if (files.length > remainingSlots) {
      setAttachmentError(
        "Maximum of 4 images allowed. Additional images were ignored.",
      );
    }

    const nextAttachments: ImageAttachment[] = [];

    for (const file of selectedFiles) {
      const validationError = validateImage(file);

      if (validationError) {
        setAttachmentError(validationError);
        continue;
      }

      try {
        const base64 = await fileToBase64(file);

        nextAttachments.push({
          id: crypto.randomUUID(),
          file,
          previewUrl: URL.createObjectURL(file),
          base64,
          mimeType: file.type,
        });
      } catch {
        setAttachmentError(`Unable to read ${file.name}.`);
      }
    }

    if (nextAttachments.length > 0) {
      setImages((current) => [...current, ...nextAttachments]);
    }
  }

  async function performPdfUpload(file: File) {
    if (chatId === null) return;

    setPdf({
      file,
      filename: file.name,
      status: "uploading",
    });

    try {
      setPdf((curr) => (curr ? { ...curr, status: "processing" } : null));

      const result = await chatActions.uploadPdf(chatId, file);

      setPdf({
        file,
        filename: result.filename,
        status: "ready",
        chunksCount: result.chunksCount,
      });
    } catch (error) {
      setPdf({
        file,
        filename: file.name,
        status: "error",
        error: error instanceof Error ? error.message : "PDF upload failed.",
      });
    }
  }

  async function handlePdfSelection(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    clearAttachmentError();

    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file || chatId === null) {
      return;
    }

    const validationError = validatePdf(file);

    if (validationError) {
      setAttachmentError(validationError);
      return;
    }

    await performPdfUpload(file);
  }

  function handleRetryPdf() {
    if (!pdf?.file) return;
    void performPdfUpload(pdf.file);
  }

  function removeImage(id: string) {
    setImages((current) => {
      const attachment = current.find((item) => item.id === id);

      if (attachment) {
        URL.revokeObjectURL(attachment.previewUrl);
      }

      return current.filter((item) => item.id !== id);
    });
  }

  function removePdf() {
    if (chatId !== null) {
      useChatStore.getState().clearPdfState(chatId);
    }
    setPdf(null);
  }

  function clearImages() {
    for (const image of images) {
      URL.revokeObjectURL(image.previewUrl);
    }

    setImages([]);
  }

  async function handleSubmit() {
    if (!canSend || chatId === null) {
      return;
    }

    const value = prompt.trim();

    const imageBase64 = images.map((image) => image.base64);
    const imageMime = images.map((image) => image.mimeType);

    setPrompt("");

    try {
      await chatActions.sendMessage({
        chatId,
        prompt: value,
        imageBase64: imageBase64.length > 0 ? imageBase64 : undefined,
        imageMime: imageMime.length > 0 ? imageMime : undefined,
      });

      clearImages();
    } catch {
      // Handled in chatActions
    }
  }

  function handleStop() {
    chatActions.stopStreaming();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background pb-[max(0px,env(safe-area-inset-bottom))]">
      <div className="mx-auto w-full max-w-3xl px-2.5 py-2.5 sm:px-4 sm:py-4">
        <div
          className={cn(
            "relative overflow-hidden rounded-2xl border border-border bg-card",
            "shadow-sm transition-colors",
            "focus-within:border-ring",
          )}
        >
          <ImageAttachmentList
            attachments={images}
            onRemove={removeImage}
            disabled={isStreaming}
          />

          {pdf && (
            <PdfAttachmentView
              attachment={pdf}
              onRemove={removePdf}
              onRetry={handleRetryPdf}
            />
          )}

          {attachmentError && (
            <div className="px-3 pt-3" role="alert">
              <p className="text-xs text-destructive">{attachmentError}</p>
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={chatId === null || isStreaming || isUploadingOrProcessing}
            placeholder={
              chatId === null ? "Start a new chat" : "Message AI Engine…"
            }
            aria-label="Chat prompt"
            rows={1}
            className={cn(
              "block max-h-55 min-h-14 w-full resize-none",
              "bg-transparent px-4 pb-14 pt-4",
              "text-sm leading-6 text-foreground",
              "outline-none placeholder:text-muted-foreground",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />

          <div className="absolute bottom-2 left-2 flex items-center gap-1">
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              disabled={
                chatId === null ||
                isStreaming ||
                isUploadingOrProcessing ||
                images.length >= 4
              }
              aria-label="Attach image"
              title="Attach image"
              className={cn(
                "flex size-10 items-center justify-center rounded-xl sm:size-9",
                "text-muted-foreground",
                "transition-colors hover:bg-secondary hover:text-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                "disabled:pointer-events-none disabled:opacity-40",
              )}
            >
              <ImagePlus className="size-4" />
            </button>

            <button
              type="button"
              onClick={() => pdfInputRef.current?.click()}
              disabled={
                chatId === null ||
                isStreaming ||
                isUploadingOrProcessing ||
                pdf !== null
              }
              aria-label="Attach PDF"
              title="Attach PDF"
              className={cn(
                "flex size-10 items-center justify-center rounded-xl sm:size-9",
                "text-muted-foreground",
                "transition-colors hover:bg-secondary hover:text-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                "disabled:pointer-events-none disabled:opacity-40",
              )}
            >
              {isUploadingOrProcessing ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <FilePlus2 className="size-4" />
              )}
            </button>
          </div>

          <div className="absolute bottom-2 right-2">
            {isStreaming ? (
              <button
                type="button"
                onClick={handleStop}
                aria-label="Stop generating"
                title="Stop generating"
                className={cn(
                  "flex size-10 items-center justify-center sm:size-9",
                  "rounded-xl bg-secondary text-foreground",
                  "transition-colors hover:bg-muted",
                  "focus-visible:outline-none",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                <Square className="size-4 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={!canSend}
                aria-label="Send message"
                title="Send message"
                className={cn(
                  "flex size-10 items-center justify-center sm:size-9",
                  "rounded-xl bg-primary text-primary-foreground",
                  "transition-opacity hover:opacity-90",
                  "focus-visible:outline-none",
                  "focus-visible:ring-2 focus-visible:ring-ring",
                  "disabled:pointer-events-none disabled:opacity-40",
                )}
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>

          <input
            ref={imageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={handleImageSelection}
          />

          <input
            ref={pdfInputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={handlePdfSelection}
          />
        </div>

        <p className="mt-2 text-center text-xs text-muted-foreground">
          Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  );
}
