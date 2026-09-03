import { create } from "zustand";

import type { ChatSession } from "@/types/api";

interface ChatSessionStore {
  sessions: ChatSession[];
  isLoading: boolean;
  error: string | null;
  mutatingChatIds: Record<number, boolean>;

  setSessions: (sessions: ChatSession[]) => void;
  addSession: (session: ChatSession) => void;
  updateSession: (chatId: number, updates: Partial<ChatSession>) => void;
  promoteSession: (chatId: number, updates?: Partial<ChatSession>) => void;
  removeSession: (chatId: number) => void;

  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setChatMutating: (chatId: number, mutating: boolean) => void;
  reset: () => void;
}

export const useChatSessionStore = create<ChatSessionStore>((set) => ({
  sessions: [],
  isLoading: false,
  error: null,
  mutatingChatIds: {},

  setSessions: (sessions) =>
    set({
      sessions,
      error: null,
    }),

  addSession: (session) =>
    set((state) => ({
      sessions: [
        session,
        ...state.sessions.filter((existing) => existing.id !== session.id),
      ],
    })),

  updateSession: (chatId, updates) =>
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === chatId ? { ...session, ...updates } : session,
      ),
    })),

  promoteSession: (chatId, updates = {}) =>
    set((state) => {
      const session = state.sessions.find((item) => item.id === chatId);
      if (!session) return state;

      const updatedSession = { ...session, ...updates };

      return {
        sessions: [
          updatedSession,
          ...state.sessions.filter((item) => item.id !== chatId),
        ],
      };
    }),

  removeSession: (chatId) =>
    set((state) => ({
      sessions: state.sessions.filter((session) => session.id !== chatId),
    })),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  setChatMutating: (chatId, mutating) =>
    set((state) => {
      const mutatingChatIds = { ...state.mutatingChatIds };
      if (mutating) {
        mutatingChatIds[chatId] = true;
      } else {
        delete mutatingChatIds[chatId];
      }
      return { mutatingChatIds };
    }),

  reset: () =>
    set({
      sessions: [],
      isLoading: false,
      error: null,
      mutatingChatIds: {},
    }),
}));