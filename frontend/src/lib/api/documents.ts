import { apiClient } from "./client";
import type { Document, DocumentMetadataUpdate } from "@/types/api";
import { normalizeDocument } from "@/features/documents/document-utils";

export const documentApi = {
  async listForChat(chatId: number): Promise<Document[]> {
    const raw = await apiClient.get<Record<string, unknown>[]>(`/documents/chat/${chatId}`);
    return (raw ?? []).map((item) => normalizeDocument(item));
  },

  async get(documentId: number): Promise<Document> {
    const raw = await apiClient.get<Record<string, unknown>>(`/documents/${documentId}`);
    return normalizeDocument(raw);
  },

  async update(documentId: number, payload: DocumentMetadataUpdate): Promise<Document> {
    const raw = await apiClient.patch<Record<string, unknown>>(`/documents/${documentId}`, payload);
    return normalizeDocument(raw);
  },

  async delete(documentId: number): Promise<void> {
    await apiClient.delete<void>(`/documents/${documentId}`);
  },
};