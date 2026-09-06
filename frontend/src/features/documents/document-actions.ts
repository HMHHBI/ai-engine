import { documentApi } from "@/lib/api/documents";
import { useDocumentStore } from "./document-store";
import type { Document, DocumentMetadataUpdate } from "@/types/api";

export async function loadDocuments(chatId: number): Promise<Document[]> {
  const store = useDocumentStore.getState();
  store.setLoading(chatId, true);
  store.setError(chatId, null);

  try {
    const docs = await documentApi.listForChat(chatId);
    store.setDocuments(chatId, docs);
    return docs;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Failed to load documents";
    store.setError(chatId, message);
    throw err;
  } finally {
    store.setLoading(chatId, false);
  }
}

export async function loadDocument(documentId: number): Promise<Document> {
  const doc = await documentApi.get(documentId);
  useDocumentStore.getState().addDocument(doc);
  return doc;
}

export async function updateDocument(
  documentId: number,
  payload: DocumentMetadataUpdate
): Promise<Document> {
  const store = useDocumentStore.getState();
  store.setDocumentMutating(documentId, true);

  try {
    const updated = await documentApi.update(documentId, payload);
    store.updateDocumentInStore(updated);
    return updated;
  } finally {
    store.setDocumentMutating(documentId, false);
  }
}

export async function deleteDocument(chatId: number, documentId: number): Promise<void> {
  const store = useDocumentStore.getState();
  store.setDocumentMutating(documentId, true);

  try {
    await documentApi.delete(documentId);
    store.removeDocumentFromStore(chatId, documentId);
  } finally {
    store.setDocumentMutating(documentId, false);
  }
}

export function selectDocument(chatId: number, documentId: number | null): void {
  useDocumentStore.getState().setSelectedDocument(chatId, documentId);
}

export function clearDocumentSelection(chatId: number): void {
  useDocumentStore.getState().clearSelectedDocument(chatId);
}