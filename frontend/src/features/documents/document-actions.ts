import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { documentApi } from "@/lib/api/documents";
import { useDocumentStore } from "./document-store";
import type {
  Document,
  DocumentMetadataUpdate,
  PdfUploadResponse,
} from "@/types/api";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";

const documentPollingControllers =
  new Map<number, AbortController>();

const POLLING_DELAYS_MS = [
  1000,
  2000,
  4000,
  8000,
  10000,
];

const MAX_POLL_DURATION_MS = 5 * 60 * 1000;

function waitForPollingDelay(
  delayMs: number,
  signal: AbortSignal,
): Promise<boolean> {
  if (signal.aborted) {
    return Promise.resolve(false);
  }

  return new Promise<boolean>((resolve) => {
    let timeoutId: ReturnType<typeof setTimeout> | null =
      null;

    const cleanup = () => {
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
      }

      signal.removeEventListener(
        "abort",
        onAbort,
      );
    };

    const onAbort = () => {
      cleanup();
      resolve(false);
    };

    signal.addEventListener(
      "abort",
      onAbort,
      { once: true },
    );

    timeoutId = setTimeout(() => {
      cleanup();
      resolve(true);
    }, delayMs);
  });
}

export function stopDocumentPolling(
  documentId: number,
): void {
  const controller =
    documentPollingControllers.get(
      documentId,
    );

  if (!controller) {
    return;
  }

  controller.abort();
  documentPollingControllers.delete(
    documentId,
  );
}

export async function loadDocuments(
  chatId: number,
): Promise<Document[]> {
  const store = useDocumentStore.getState();

  store.setLoading(chatId, true);
  store.setError(chatId, null);

  try {
    const docs =
      await documentApi.listForChat(chatId);

    store.setDocuments(chatId, docs);

    return docs;
  } catch (err: unknown) {
    const message =
      err instanceof Error
        ? err.message
        : "Failed to load documents";

    store.setError(chatId, message);

    throw err;
  } finally {
    store.setLoading(chatId, false);
  }
}

export async function loadDocument(
  documentId: number,
): Promise<Document> {
  const doc =
    await documentApi.get(documentId);

  useDocumentStore
    .getState()
    .addDocument(doc);

  return doc;
}

export async function updateDocument(
  documentId: number,
  payload: DocumentMetadataUpdate,
): Promise<Document> {
  const store =
    useDocumentStore.getState();

  store.setDocumentMutating(
    documentId,
    true,
  );

  try {
    const updated =
      await documentApi.update(
        documentId,
        payload,
      );

    store.updateDocumentInStore(
      updated,
    );

    return updated;
  } finally {
    useDocumentStore
      .getState()
      .setDocumentMutating(
        documentId,
        false,
      );
  }
}

export async function deleteDocument(
  chatId: number,
  documentId: number,
): Promise<void> {
  const store =
    useDocumentStore.getState();

  stopDocumentPolling(
    documentId,
  );

  store.setDocumentMutating(
    documentId,
    true,
  );

  try {
    await documentApi.delete(
      documentId,
    );

    store.removeDocumentFromStore(
      chatId,
      documentId,
    );
  } finally {
    useDocumentStore
      .getState()
      .setDocumentMutating(
        documentId,
        false,
      );
  }
}

export async function retryDocument(
  chatId: number,
  documentId: number,
): Promise<Document> {
  const store =
    useDocumentStore.getState();

  stopDocumentPolling(
    documentId,
  );

  store.setDocumentMutating(
    documentId,
    true,
  );

  store.setError(
    chatId,
    null,
  );

  try {
    const response =
      await documentApi.retry(
        documentId,
      );

    store.updateDocumentInStore(
      response,
    );

    if (
      response.status !== "ready" &&
      response.status !== "failed"
    ) {
      void pollDocumentUntilResolved(
        chatId,
        documentId,
      );
    }

    return response;
  } catch (err: unknown) {
    const message =
      err instanceof Error
        ? err.message
        : "Document retry failed.";

    store.setError(
      chatId,
      message,
    );

    throw err;
  } finally {
    useDocumentStore
      .getState()
      .setDocumentMutating(
        documentId,
        false,
      );
  }
}

export function selectDocument(
  chatId: number,
  documentId: number | null,
): boolean {
  const store =
    useDocumentStore.getState();

  const currentSelected =
    store.selectedDocumentIdByChat[
      chatId
    ] ?? null;

  if (documentId === null) {
    if (currentSelected !== null) {
      chatRequestController.invalidate();
    }

    store.clearSelectedDocument(
      chatId,
    );

    return true;
  }

  const document = (
    store.documentsByChat[chatId] ?? []
  ).find(
    (item) =>
      item.id === documentId,
  );

  if (
    !document ||
    document.status !== "ready"
  ) {
    return false;
  }

  if (
    currentSelected === documentId
  ) {
    chatRequestController.invalidate();

    store.clearSelectedDocument(
      chatId,
    );

    return true;
  }

  chatRequestController.invalidate();

  store.setSelectedDocument(
    chatId,
    documentId,
  );

  return true;
}

export function clearDocumentSelection(
  chatId: number,
): void {
  const store =
    useDocumentStore.getState();

  const currentSelected =
    store.selectedDocumentIdByChat[
      chatId
    ] ?? null;

  if (currentSelected !== null) {
    chatRequestController.invalidate();
  }

  store.clearSelectedDocument(
    chatId,
  );
}

export const MAX_FILE_SIZE_BYTES =
  10 * 1024 * 1024;

export function validatePdfFile(
  file: File,
): { valid: boolean; error?: string } {
  if (!file || !file.name) {
    return {
      valid: false,
      error: "No file selected.",
    };
  }

  if (
    !file.name
      .toLowerCase()
      .endsWith(".pdf")
  ) {
    return {
      valid: false,
      error:
        "Only PDF files are supported.",
    };
  }

  if (
    file.type &&
    file.type !== "application/pdf"
  ) {
    return {
      valid: false,
      error:
        "Invalid file MIME type. Only PDF is accepted.",
    };
  }

  if (file.size <= 0) {
    return {
      valid: false,
      error: "File is empty.",
    };
  }

  if (
    file.size >
    MAX_FILE_SIZE_BYTES
  ) {
    return {
      valid: false,
      error:
        "File size exceeds the 10 MiB limit.",
    };
  }

  return { valid: true };
}

export async function pollDocumentUntilResolved(
  chatId: number,
  targetDocumentId?: number,
): Promise<void> {
  if (
    targetDocumentId !== undefined
  ) {
    stopDocumentPolling(
      targetDocumentId,
    );
  }

  const controller =
    new AbortController();

  if (
    targetDocumentId !== undefined
  ) {
    documentPollingControllers.set(
      targetDocumentId,
      controller,
    );
  }

  const signal =
    controller.signal;

  const startedAt = Date.now();

  try {
    let stepIndex = 0;

    while (
      Date.now() - startedAt <
        MAX_POLL_DURATION_MS &&
      !signal.aborted
    ) {
      const delay =
        POLLING_DELAYS_MS[
          Math.min(
            stepIndex,
            POLLING_DELAYS_MS.length - 1,
          )
        ];

      stepIndex += 1;

      const shouldContinue =
        await waitForPollingDelay(
          delay,
          signal,
        );

      if (
        !shouldContinue ||
        signal.aborted
      ) {
        return;
      }

      if (
        Date.now() - startedAt >=
        MAX_POLL_DURATION_MS
      ) {
        return;
      }

      try {
        const docs =
          await documentApi.listForChat(
            chatId,
            { signal },
          );

        if (signal.aborted) {
          return;
        }

        const target =
          targetDocumentId !== undefined
            ? docs.find(
                (document) =>
                  document.id ===
                  targetDocumentId,
              )
            : docs.find(
                (document) =>
                  document.status !==
                    "ready" &&
                  document.status !==
                    "failed",
              );

        if (
          !target ||
          target.status ===
            "ready" ||
          target.status ===
            "failed"
        ) {
          if (!signal.aborted) {
            useDocumentStore
              .getState()
              .setDocuments(
                chatId,
                docs,
              );
          }

          return;
        }

        if (!signal.aborted) {
          useDocumentStore
            .getState()
            .setDocuments(
              chatId,
              docs,
            );
        }
      } catch (error) {
        if (
          signal.aborted
        ) {
          return;
        }

        if (
          error instanceof DOMException &&
          error.name ===
            "AbortError"
        ) {
          return;
        }
      }
    }
  } finally {
    if (
      targetDocumentId !==
      undefined &&
      documentPollingControllers.get(
        targetDocumentId,
      ) === controller
    ) {
      documentPollingControllers.delete(
        targetDocumentId,
      );
    }
  }
}

export async function uploadDocument(
  chatId: number,
  file: File,
): Promise<PdfUploadResponse> {
  const validation =
    validatePdfFile(file);

  if (!validation.valid) {
    throw new Error(
      validation.error ??
        "Invalid PDF file.",
    );
  }

  const store =
    useDocumentStore.getState();

  if (
    store.uploadingByChat[chatId]
  ) {
    throw new Error(
      "An upload is already in progress for this chat.",
    );
  }

  store.setUploading(
    chatId,
    true,
  );

  store.setError(
    chatId,
    null,
  );

  try {
    const response =
      await documentApi.upload(
        chatId,
        file,
      );

    store.addDocument(
      response,
    );

    const sessionStore =
      useChatSessionStore.getState();

    const existingSession =
      sessionStore.sessions.find(
        (session) =>
          session.id === chatId,
      );

    if (existingSession) {
      const nextDocuments =
        useDocumentStore
          .getState()
          .documentsByChat[
            chatId
          ] ?? [];

      const cleanTitle =
        response.filename
          .replace(/\.[^.]+$/, "")
          .replace(/[_-]+/g, " ")
          .trim();

      sessionStore.updateSession(
        chatId,
        {
          title:
            existingSession.title ===
            "New Chat"
              ? cleanTitle
              : existingSession.title,
          attached_documents_count:
            nextDocuments.length,
          primary_document_title:
            nextDocuments.length === 1
              ? response.filename
              : existingSession.primary_document_title,
          last_active_at:
            response.updated_at,
          updated_at:
            response.updated_at,
        },
      );
    }

    if (
      response.status !==
        "ready" &&
      response.status !==
        "failed"
    ) {
      void pollDocumentUntilResolved(
        chatId,
        response.id,
      );
    }

    return {
      status: response.status,
      filename: response.filename,
      chunks_total: 0,
      chunks_indexed: 0,
      chunks_failed:
        response.status ===
        "failed"
          ? 1
          : 0,
      embedding_provider: "",
      message:
        response.error_message ??
        "Document uploaded.",
      document: response,
    };
  } catch (err: unknown) {
    const message =
      err instanceof Error
        ? err.message
        : "Document upload failed.";

    store.setError(
      chatId,
      message,
    );

    throw err;
  } finally {
    store.setUploading(
      chatId,
      false,
    );
  }
}
