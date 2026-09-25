import { apiClient } from "./client";
import type {
  Document,
  DocumentLifecycleResponse,
  DocumentMetadataUpdate,
} from "@/types/api";
import { normalizeDocument } from "@/features/documents/document-utils";

function normalizeLifecycleResponse(
  raw: Record<string, unknown>,
): DocumentLifecycleResponse {
  const document = normalizeDocument(raw);

  const rawJob = raw.job;

  if (!rawJob || typeof rawJob !== "object") {
    return {
      ...document,
      job: null,
    };
  }

  const job = rawJob as Record<string, unknown>;

  return {
    ...document,
    job: {
      id: Number(job.id),
      document_id: Number(job.document_id),
      status: String(job.status) as
        | "queued"
        | "processing"
        | "ready"
        | "failed"
        | "cancelled",
      attempt: Number(job.attempt ?? 0),
      max_attempts: Number(job.max_attempts ?? 3),
      error_message:
        typeof job.error_message === "string"
          ? job.error_message
          : null,
      queued_at: String(job.queued_at ?? document.created_at),
      started_at:
        typeof job.started_at === "string"
          ? job.started_at
          : null,
      finished_at:
        typeof job.finished_at === "string"
          ? job.finished_at
          : null,
    },
  };
}

export const documentApi = {
  async listForChat(chatId: number): Promise<Document[]> {
    const raw = await apiClient.get<Record<string, unknown>[]>(
      `/documents/chat/${chatId}`,
    );

    return (raw ?? []).map((item) => normalizeDocument(item));
  },

  async get(documentId: number): Promise<Document> {
    const raw = await apiClient.get<Record<string, unknown>>(
      `/documents/${documentId}`,
    );

    return normalizeDocument(raw);
  },

  async upload(
    chatId: number,
    file: File,
  ): Promise<DocumentLifecycleResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const raw = await apiClient.post<Record<string, unknown>>(
      `/documents/chat/${chatId}/upload`,
      formData,
    );

    return normalizeLifecycleResponse(raw);
  },

  async retry(
    documentId: number,
  ): Promise<DocumentLifecycleResponse> {
    const raw = await apiClient.post<Record<string, unknown>>(
      `/documents/${documentId}/retry`,
      {},
    );

    return normalizeLifecycleResponse(raw);
  },

  async getFile(
    documentId: number,
    options?: RequestInit,
  ): Promise<Blob> {
    return options
      ? apiClient.getBlob(`/documents/${documentId}/file`, options)
      : apiClient.getBlob(`/documents/${documentId}/file`);
  },

  async update(
    documentId: number,
    payload: DocumentMetadataUpdate,
  ): Promise<Document> {
    const raw = await apiClient.patch<Record<string, unknown>>(
      `/documents/${documentId}`,
      payload,
    );

    return normalizeDocument(raw);
  },

  async delete(documentId: number): Promise<void> {
    await apiClient.delete<void>(`/documents/${documentId}`);
  },
};
