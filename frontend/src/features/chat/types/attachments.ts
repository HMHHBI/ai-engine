export interface ImageAttachment {
  id: string;
  file: File;
  previewUrl: string;
  base64: string;
  mimeType: string;
}

export type PdfUploadStatus =
  | "idle"
  | "validating"
  | "uploading"
  | "processing"
  | "ready"
  | "error";

export interface PdfAttachment {
  file: File;
  filename: string;
  status: PdfUploadStatus;
  chunksCount?: number;
  error?: string;
}