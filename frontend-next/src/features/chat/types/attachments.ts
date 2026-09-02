export interface ImageAttachment {
  id: string;
  file: File;
  previewUrl: string;
  base64: string;
  mimeType: string;
}

export interface PdfAttachment {
  file: File;
  filename: string;
  status: "idle" | "uploading" | "uploaded" | "error";
  chunksCount?: number;
  error?: string;
}