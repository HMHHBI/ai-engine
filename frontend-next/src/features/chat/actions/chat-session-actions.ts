import { chatApi } from "@/lib/api/chat";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";

class ChatSessionActions {
  private hydrationGeneration = 0;

  async loadChats(): Promise<void> {
    const sessionStore = useChatSessionStore.getState();

    sessionStore.setLoading(true);
    sessionStore.setError(null);

    try {
      const sessions = await chatApi.getAll();

      const sortedSessions = [...sessions].sort(
        (a, b) =>
          new Date(b.updated_at).getTime() -
          new Date(a.updated_at).getTime(),
      );

      useChatSessionStore
        .getState()
        .setSessions(sortedSessions);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to load chat history.";

      useChatSessionStore
        .getState()
        .setError(message);

      throw error;
    } finally {
      useChatSessionStore
        .getState()
        .setLoading(false);
    }
  }

  async createChat(): Promise<number> {
    const chat = await chatApi.create();

    useChatStore
      .getState()
      .setActiveChat(chat.id);

    useChatStore
      .getState()
      .setMessages(chat.id, []);

    useChatSessionStore
      .getState()
      .addSession(chat);

    return chat.id;
  }

  async loadChat(chatId: number): Promise<boolean> {
    const requestGeneration = ++this.hydrationGeneration;

    useChatStore.getState().setChatLoading(chatId, true);

    try {
      const messages = await chatApi.get(chatId);

      if (requestGeneration !== this.hydrationGeneration) {
        return false;
      }

      useChatStore.getState().setMessages(chatId, messages);
      useChatStore.getState().setActiveChat(chatId);

      return true;
    } finally {
      if (requestGeneration === this.hydrationGeneration) {
        useChatStore.getState().setChatLoading(chatId, false);
      }
    }
  }

  invalidateHydration(): void {
    this.hydrationGeneration += 1;
  }

  clearActiveChat(): void {
    this.invalidateHydration();
    useChatStore.getState().setActiveChat(null);
  }
}

export const chatSessionActions = new ChatSessionActions();