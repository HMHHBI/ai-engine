import { documentApi } from "@/lib/api/documents";
import { chatApi } from "@/lib/api/chat";
import { useDocumentStore } from "./document-store";
import type { Document, DocumentMetadataUpdate, PdfUploadResponse } from "@/types/api";

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

// ==========================================
// F3-B.3: Validation, Upload & Lifecycle
// ==========================================

export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50MB

export function validatePdfFile(file: File): { valid: boolean; error?: string } {
  if (!file || !file.name) {
    return { valid: false, error: "No file selected." };
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return { valid: false, error: "Only PDF files are supported." };
  }
  if (file.type && file.type !== "application/pdf") {
    return { valid: false, error: "Invalid file MIME type. Only PDF is accepted." };
  }
  if (file.size <= 0) {
    return { valid: false, error: "File is empty." };
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return { valid: false, error: "File size exceeds the 50MB limit." };
  }
  return { valid: true };
}

const POLLING_DELAYS_MS = [1000, 2000, 3000, 5000];
const MAX_POLL_DURATION_MS = 60000;

export async function pollDocumentUntilResolved(
  chatId: number,
  targetDocumentId?: number
): Promise<void> {
  const startTime = Date.now();
  let stepIndex = 0;

  return new Promise<void>((resolve) => {
    async function check() {
      if (Date.now() - startTime >= MAX_POLL_DURATION_MS) {
        resolve();
        return;
      }

      try {
        const docs = await documentApi.listForChat(chatId);
        useDocumentStore.getState().setDocuments(chatId, docs);

        const target = targetDocumentId
          ? docs.find((d) => d.id === targetDocumentId)
          : docs.find((d) => d.status === "processing");

        if (!target || target.status === "ready" || target.status === "failed") {
          resolve();
          return;
        }
      } catch {
        // Polling gracefully ignores intermediate network blips
      }

      const delay = POLLING_DELAYS_MS[Math.min(stepIndex, POLLING_DELAYS_MS.length - 1)];
      stepIndex++;
      setTimeout(check, delay);
    }

    setTimeout(check, POLLING_DELAYS_MS[0]);
  });
}

export async function uploadDocument(
  chatId: number,
  file: File
): Promise<PdfUploadResponse> {
  const validation = validatePdfFile(file);
  if (!validation.valid) {
    throw new Error(validation.error || "Invalid PDF file.");
  }

  const store = useDocumentStore.getState();
  if (store.uploadingByChat[chatId]) {
    throw new Error("An upload is already in progress for this chat.");
  }

  store.setUploading(chatId, true);
  store.setError(chatId, null);

  try {
    const rawRes = await chatApi.uploadPdf(chatId, file);
    const response = rawRes as unknown as PdfUploadResponse;

    // Refresh authoritative documents list
    const updatedDocs = await documentApi.listForChat(chatId);
    store.setDocuments(chatId, updatedDocs);

    // If backend returns status as processing, initiate bounded polling
    const targetDoc = response.document?.id
      ? updatedDocs.find((d) => d.id === response.document?.id)
      : updatedDocs.find((d) => d.status === "processing");

    if (targetDoc && targetDoc.status === "processing") {
      pollDocumentUntilResolved(chatId, targetDoc.id).catch(() => {});
    }

    return response;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Document upload failed.";
    store.setError(chatId, message);
    throw err;
  } finally {
    store.setUploading(chatId, false);
  }
}