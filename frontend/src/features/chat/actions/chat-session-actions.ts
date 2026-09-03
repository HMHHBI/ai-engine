import { chatApi } from "@/lib/api/chat";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import type { ChatMessage, ChatSession } from "@/types/api";

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

      useChatSessionStore.getState().setSessions(sortedSessions);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to load chat history.";

      useChatSessionStore.getState().setError(message);
      throw error;
    } finally {
      useChatSessionStore.getState().setLoading(false);
    }
  }

  async createChat(): Promise<number> {
    const response = await chatApi.create();
    const chatId = response.chat_id;
    const now = new Date().toISOString();

    const session: ChatSession = {
      id: chatId,
      user_id: 0,
      title: "New Chat",
      created_at: now,
      updated_at: now,
      has_pdf: false,
    };

    useChatStore.getState().setMessages(chatId, []);
    useChatSessionStore.getState().addSession(session);

    return chatId;
  }

  syncFirstMessageTitle(chatId: number, prompt: string): void {
    const sessionStore = useChatSessionStore.getState();
    const session = sessionStore.sessions.find((item) => item.id === chatId);

    if (!session || session.title !== "New Chat") {
      return;
    }

    const normalizedPrompt = prompt.trim();
    if (!normalizedPrompt) {
      return;
    }

    const title =
      normalizedPrompt.length > 25
        ? `${normalizedPrompt.slice(0, 25)}...`
        : normalizedPrompt;

    sessionStore.promoteSession(chatId, {
      title,
      updated_at: new Date().toISOString(),
    });
  }

  async renameChat(chatId: number, title: string): Promise<void> {
    const normalizedTitle = title.trim();

    if (!normalizedTitle) {
      throw new Error("Chat title cannot be empty.");
    }

    const sessionStore = useChatSessionStore.getState();
    sessionStore.setChatMutating(chatId, true);

    try {
      await chatApi.updateTitle(chatId, normalizedTitle);

      useChatSessionStore.getState().updateSession(chatId, {
        title: normalizedTitle,
        updated_at: new Date().toISOString(),
      });
    } finally {
      useChatSessionStore.getState().setChatMutating(chatId, false);
    }
  }

  async deleteChat(chatId: number): Promise<boolean> {
    const wasActive = useChatStore.getState().activeChatId === chatId;
    const sessionStore = useChatSessionStore.getState();

    sessionStore.setChatMutating(chatId, true);

    try {
      await chatApi.delete(chatId);

      useChatSessionStore.getState().removeSession(chatId);
      useChatStore.getState().removeChat(chatId);

      if (wasActive) {
        this.clearActiveChat();
      }

      return wasActive;
    } finally {
      useChatSessionStore.getState().setChatMutating(chatId, false);
    }
  }

  async loadChat(chatId: number): Promise<boolean> {
    chatRequestController.invalidate();

    const requestGeneration = ++this.hydrationGeneration;

    useChatStore.getState().setChatLoading(chatId, true);

    try {
      const rawMessages = await chatApi.get(chatId);

      if (requestGeneration !== this.hydrationGeneration) {
        return false;
      }

      // Normalize 'text' from backend to 'content'
      const normalizedMessages: ChatMessage[] = (rawMessages || []).map((msg) => ({
        ...msg,
        content: msg.content ?? msg.text ?? "",
      }));

      useChatStore.getState().setMessages(chatId, normalizedMessages);
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
    const activeChatId = useChatStore.getState().activeChatId;
    if (activeChatId !== null) {
      useChatStore.getState().setChatLoading(activeChatId, false);
    }

    chatRequestController.invalidate();
    this.invalidateHydration();
    useChatStore.getState().setActiveChat(null);
  }
}

export const chatSessionActions = new ChatSessionActions();