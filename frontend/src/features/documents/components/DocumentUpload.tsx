"use client";

import React, { useRef, useState } from "react";
import { Upload, Loader2, AlertCircle } from "lucide-react";
import { uploadDocument, validatePdfFile } from "../document-actions";
import { useDocumentStore } from "../document-store";

interface DocumentUploadProps {
  chatId: number;
  className?: string;
  onUploadSuccess?: () => void;
}

export function DocumentUpload({
  chatId,
  className = "",
  onUploadSuccess,
}: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const isUploading = useDocumentStore(
    (state) => state.uploadingByChat[chatId] ?? false,
  );

  const handleButtonClick = () => {
    setLocalError(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Clear file input immediately so re-uploading the same file works
    e.target.value = "";

    const validation = validatePdfFile(file);
    if (!validation.valid) {
      setLocalError(validation.error ?? "Invalid PDF file.");
      return;
    }

    setLocalError(null);

    try {
      await uploadDocument(chatId, file);
      onUploadSuccess?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setLocalError(msg);
    }
  };

  return (
    <div
      className={`w-full ${className}`}
      data-testid="document-upload-container"
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={handleFileChange}
        disabled={isUploading}
        data-testid="document-upload-file-input"
        aria-label="Select PDF to upload"
      />

      <button
        type="button"
        onClick={handleButtonClick}
        disabled={isUploading}
        aria-busy={isUploading}
        aria-live="polite"
        className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium text-white bg-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-sm transition-colors"
        data-testid="document-upload-button"
      >
        {isUploading ? (
          <>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>Uploading…</span>
          </>
        ) : (
          <>
            <Upload className="w-3.5 h-3.5" />
            <span>Upload PDF</span>
          </>
        )}
      </button>

      {localError && (
        <div
          role="alert"
          className="mt-2 p-2.5 rounded-lg bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-center gap-2 text-xs text-rose-700 dark:text-rose-400"
          data-testid="document-upload-error"
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{localError}</span>
        </div>
      )}
    </div>
  );
}
