import { create } from "zustand";

import type { ChatMessage } from "@/types/api";
import type { PdfUploadStatus } from "@/features/chat/types/attachments";

export type StreamingStatus =
  | "idle"
  | "streaming"
  | "completed"
  | "cancelled"
  | "error";

export interface ChatPdfState {
  status: PdfUploadStatus;
  filename: string | null;
  chunksCount: number | null;
  error: string | null;
}

interface ChatStoreState {
  activeChatId: number | null;
  messagesByChat: Record<number, ChatMessage[]>;
  loadingChatIds: Record<number, boolean>;
  streamingStatusByChat: Record<number, StreamingStatus>;
  pdfStateByChat: Record<number, ChatPdfState>;

  setActiveChat: (chatId: number | null) => void;
  setChatLoading: (chatId: number, loading: boolean) => void;
  setMessages: (chatId: number, messages: ChatMessage[]) => void;
  addMessage: (chatId: number, message: ChatMessage) => void;
  appendToLastMessage: (chatId: number, chunk: string) => void;
  setStreamingStatus: (chatId: number, status: StreamingStatus) => void;
  setPdfState: (chatId: number, state: Partial<ChatPdfState>) => void;
  clearPdfState: (chatId: number) => void;
  removeChat: (chatId: number) => void;
  reset: () => void;
}

const DEFAULT_PDF_STATE: ChatPdfState = {
  status: "idle",
  filename: null,
  chunksCount: null,
  error: null,
};

export const useChatStore = create<ChatStoreState>((set) => ({
  activeChatId: null,
  messagesByChat: {},
  loadingChatIds: {},
  streamingStatusByChat: {},
  pdfStateByChat: {},

  setActiveChat: (chatId) => set({ activeChatId: chatId }),

  setChatLoading: (chatId, loading) =>
    set((state) => {
      const nextLoading = { ...state.loadingChatIds };
      if (loading) {
        nextLoading[chatId] = true;
      } else {
        delete nextLoading[chatId];
      }
      return { loadingChatIds: nextLoading };
    }),

  setMessages: (chatId, messages) =>
    set((state) => ({
      messagesByChat: { ...state.messagesByChat, [chatId]: messages },
    })),

  addMessage: (chatId, message) =>
    set((state) => ({
      messagesByChat: {
        ...state.messagesByChat,
        [chatId]: [...(state.messagesByChat[chatId] ?? []), message],
      },
    })),

  appendToLastMessage: (chatId, chunk) =>
    set((state) => {
      const messages = state.messagesByChat[chatId] ?? [];
      if (messages.length === 0) return state;

      const last = messages[messages.length - 1];
      const updatedLast = {
        ...last,
        content: `${last.content}${chunk}`,
      };

      return {
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: [...messages.slice(0, -1), updatedLast],
        },
      };
    }),

  setStreamingStatus: (chatId, status) =>
    set((state) => ({
      streamingStatusByChat: {
        ...state.streamingStatusByChat,
        [chatId]: status,
      },
    })),

  setPdfState: (chatId, nextState) =>
    set((state) => {
      const current = state.pdfStateByChat[chatId] ?? DEFAULT_PDF_STATE;
      return {
        pdfStateByChat: {
          ...state.pdfStateByChat,
          [chatId]: { ...current, ...nextState },
        },
      };
    }),

  clearPdfState: (chatId) =>
    set((state) => {
      const copy = { ...state.pdfStateByChat };
      delete copy[chatId];
      return { pdfStateByChat: copy };
    }),

  removeChat: (chatId) =>
    set((state) => {
      const messages = { ...state.messagesByChat };
      const loadings = { ...state.loadingChatIds };
      const streaming = { ...state.streamingStatusByChat };
      const pdfs = { ...state.pdfStateByChat };

      delete messages[chatId];
      delete loadings[chatId];
      delete streaming[chatId];
      delete pdfs[chatId];

      return {
        messagesByChat: messages,
        loadingChatIds: loadings,
        streamingStatusByChat: streaming,
        pdfStateByChat: pdfs,
        activeChatId:
          state.activeChatId === chatId ? null : state.activeChatId,
      };
    }),

  reset: () =>
    set({
      activeChatId: null,
      messagesByChat: {},
      loadingChatIds: {},
      streamingStatusByChat: {},
      pdfStateByChat: {},
    }),
}));