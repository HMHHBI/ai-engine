import { create } from "zustand";
import type { Document } from "@/types/api";

export interface DocumentState {
  documentsByChat: Record<number, Document[]>;
  selectedDocumentIdByChat: Record<number, number | null>;

  loadingByChat: Record<number, boolean>;
  uploadingByChat: Record<number, boolean>;
  mutatingDocumentIds: Record<number, boolean>;

  errorByChat: Record<number, string | null>;

  // Actions
  setDocuments: (chatId: number, documents: Document[]) => void;
  addDocument: (document: Document) => void;
  updateDocumentInStore: (document: Document) => void;
  removeDocumentFromStore: (chatId: number, documentId: number) => void;

  setSelectedDocument: (chatId: number, documentId: number | null) => void;
  clearSelectedDocument: (chatId: number) => void;

  setLoading: (chatId: number, loading: boolean) => void;
  setUploading: (chatId: number, uploading: boolean) => void;
  setDocumentMutating: (documentId: number, mutating: boolean) => void;

  setError: (chatId: number, error: string | null) => void;
  reset: () => void;
}

const initialState = {
  documentsByChat: {},
  selectedDocumentIdByChat: {},
  loadingByChat: {},
  uploadingByChat: {},
  mutatingDocumentIds: {},
  errorByChat: {},
};

export const useDocumentStore = create<DocumentState>((set) => ({
  ...initialState,

  setDocuments: (chatId, documents) =>
    set((state) => {
      const currentSelected =
        state.selectedDocumentIdByChat[chatId] ?? null;

      const selectedDocument =
        currentSelected !== null
          ? documents.find((document) => document.id === currentSelected)
          : undefined;

      const nextSelectedDocumentId =
        selectedDocument?.status === "ready"
          ? currentSelected
          : null;

      return {
        documentsByChat: {
          ...state.documentsByChat,
          [chatId]: documents,
        },
        selectedDocumentIdByChat: {
          ...state.selectedDocumentIdByChat,
          [chatId]: nextSelectedDocumentId,
        },
      };
    }),

  addDocument: (document) =>
    set((state) => {
      const existing = state.documentsByChat[document.chat_id] ?? [];
      const filtered = existing.filter((d) => d.id !== document.id);
      return {
        documentsByChat: {
          ...state.documentsByChat,
          [document.chat_id]: [document, ...filtered],
        },
      };
    }),

    updateDocumentInStore: (document) =>
      set((state) => {
        const existing =
          state.documentsByChat[document.chat_id] ?? [];
  
        const currentSelected =
          state.selectedDocumentIdByChat[document.chat_id] ?? null;
  
        const nextSelectedDocumentId =
          currentSelected === document.id &&
          document.status !== "ready"
            ? null
            : currentSelected;
  
        return {
          documentsByChat: {
            ...state.documentsByChat,
            [document.chat_id]: existing.map((item) =>
              item.id === document.id ? document : item,
            ),
          },
          selectedDocumentIdByChat: {
            ...state.selectedDocumentIdByChat,
            [document.chat_id]: nextSelectedDocumentId,
          },
        };
      }),

  removeDocumentFromStore: (chatId, documentId) =>
    set((state) => {
      const existing = state.documentsByChat[chatId] ?? [];
      const currentSelected = state.selectedDocumentIdByChat[chatId];
      return {
        documentsByChat: {
          ...state.documentsByChat,
          [chatId]: existing.filter((d) => d.id !== documentId),
        },
        selectedDocumentIdByChat: {
          ...state.selectedDocumentIdByChat,
          [chatId]: currentSelected === documentId ? null : currentSelected,
        },
      };
    }),

  setSelectedDocument: (chatId, documentId) =>
    set((state) => ({
      selectedDocumentIdByChat: {
        ...state.selectedDocumentIdByChat,
        [chatId]: documentId,
      },
    })),

  clearSelectedDocument: (chatId) =>
    set((state) => ({
      selectedDocumentIdByChat: {
        ...state.selectedDocumentIdByChat,
        [chatId]: null,
      },
    })),

  setLoading: (chatId, loading) =>
    set((state) => ({
      loadingByChat: {
        ...state.loadingByChat,
        [chatId]: loading,
      },
    })),

  setUploading: (chatId, uploading) =>
    set((state) => ({
      uploadingByChat: {
        ...state.uploadingByChat,
        [chatId]: uploading,
      },
    })),

  setDocumentMutating: (documentId, mutating) =>
    set((state) => ({
      mutatingDocumentIds: {
        ...state.mutatingDocumentIds,
        [documentId]: mutating,
      },
    })),

  setError: (chatId, error) =>
    set((state) => ({
      errorByChat: {
        ...state.errorByChat,
        [chatId]: error,
      },
    })),

  reset: () => set(initialState),
}));