import { create } from "zustand";
import type { ChatMessage } from "@/types/api";

export type ChatStreamingStatus =
  | "idle"
  | "streaming"
  | "completed"
  | "cancelled"
  | "error";

export interface ChatStore {
  activeChatId: number | null;

  messagesByChat: Record<number, ChatMessage[]>;

  streamingStatusByChat: Record<
    number,
    ChatStreamingStatus
  >;

  setActiveChat: (chatId: number | null) => void;

  setMessages: (
    chatId: number,
    messages: ChatMessage[],
  ) => void;

  addMessage: (
    chatId: number,
    message: ChatMessage,
  ) => void;

  updateLastMessage: (
    chatId: number,
    updater: (message: ChatMessage) => ChatMessage,
  ) => void;

  appendToLastMessage: (
    chatId: number,
    chunk: string,
  ) => void;

  setStreamingStatus: (
    chatId: number,
    status: ChatStreamingStatus,
  ) => void;

  clearMessages: (chatId: number) => void;

  removeChat: (chatId: number) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  activeChatId: null,

  messagesByChat: {},

  streamingStatusByChat: {},

  setActiveChat: (chatId) =>
    set({
      activeChatId: chatId,
    }),

  setMessages: (chatId, messages) =>
    set((state) => ({
      messagesByChat: {
        ...state.messagesByChat,
        [chatId]: messages,
      },
    })),

  addMessage: (chatId, message) =>
    set((state) => ({
      messagesByChat: {
        ...state.messagesByChat,
        [chatId]: [
          ...(state.messagesByChat[chatId] ?? []),
          message,
        ],
      },
    })),

  updateLastMessage: (chatId, updater) =>
    set((state) => {
      const messages = state.messagesByChat[chatId] ?? [];

      if (messages.length === 0) {
        return state;
      }

      const lastIndex = messages.length - 1;

      const updatedMessages = [...messages];

      updatedMessages[lastIndex] = updater(
        messages[lastIndex],
      );

      return {
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: updatedMessages,
        },
      };
    }),

  appendToLastMessage: (chatId, chunk) =>
    set((state) => {
      const messages = state.messagesByChat[chatId] ?? [];

      if (messages.length === 0) {
        return state;
      }

      const lastIndex = messages.length - 1;
      const lastMessage = messages[lastIndex];

      const updatedMessages = [...messages];

      updatedMessages[lastIndex] = {
        ...lastMessage,
        content: `${lastMessage.content ?? ""}${chunk}`,
      };

      return {
        messagesByChat: {
          ...state.messagesByChat,
          [chatId]: updatedMessages,
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

  clearMessages: (chatId) =>
    set((state) => ({
      messagesByChat: {
        ...state.messagesByChat,
        [chatId]: [],
      },
    })),

  removeChat: (chatId) =>
    set((state) => {
      const messagesByChat = {
        ...state.messagesByChat,
      };

      const streamingStatusByChat = {
        ...state.streamingStatusByChat,
      };

      delete messagesByChat[chatId];
      delete streamingStatusByChat[chatId];

      return {
        activeChatId:
          state.activeChatId === chatId
            ? null
            : state.activeChatId,

        messagesByChat,
        streamingStatusByChat,
      };
    }),
}));