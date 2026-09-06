import type { Document, DocumentStatus, DocumentSummary } from "@/types/api";

const VALID_STATUSES: Set<DocumentStatus> = new Set(["processing", "ready", "failed"]);

export function normalizeDocumentStatus(status: unknown): DocumentStatus {
  if (typeof status === "string" && VALID_STATUSES.has(status as DocumentStatus)) {
    return status as DocumentStatus;
  }
  return "processing";
}

export function normalizeDocument(raw: Record<string, unknown>): Document {
  return {
    id: Number(raw.id),
    user_id: Number(raw.user_id),
    chat_id: Number(raw.chat_id),
    filename: String(raw.filename ?? ""),
    mime_type: String(raw.mime_type ?? "application/octet-stream"),
    file_size: raw.file_size !== null && raw.file_size !== undefined ? Number(raw.file_size) : null,
    page_count: raw.page_count !== null && raw.page_count !== undefined ? Number(raw.page_count) : null,
    storage_url: typeof raw.storage_url === "string" ? raw.storage_url : null,
    status: normalizeDocumentStatus(raw.status),
    error_message: typeof raw.error_message === "string" ? raw.error_message : null,
    created_at: String(raw.created_at ?? new Date().toISOString()),
    updated_at: String(raw.updated_at ?? new Date().toISOString()),
  };
}

export function normalizeDocumentSummary(raw: Record<string, unknown>): DocumentSummary {
  return {
    id: Number(raw.id),
    chat_id: Number(raw.chat_id),
    filename: String(raw.filename ?? ""),
    mime_type: String(raw.mime_type ?? "application/octet-stream"),
    file_size: raw.file_size !== null && raw.file_size !== undefined ? Number(raw.file_size) : null,
    page_count: raw.page_count !== null && raw.page_count !== undefined ? Number(raw.page_count) : null,
    status: normalizeDocumentStatus(raw.status),
    created_at: String(raw.created_at ?? new Date().toISOString()),
    updated_at: String(raw.updated_at ?? new Date().toISOString()),
  };
}