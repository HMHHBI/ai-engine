import { chatApi } from "@/lib/api/chat";
import { useChatStore } from "@/features/chat/store/chat-store";

class ChatSessionActions {
  async createChat(): Promise<number> {
    const chat = await chatApi.create();

    useChatStore.getState().setActiveChat(chat.id);
    useChatStore.getState().setMessages(chat.id, []);

    return chat.id;
  }

  async loadChat(chatId: number): Promise<void> {
    const messages = await chatApi.get(chatId);

    useChatStore.getState().setMessages(chatId, messages);
    useChatStore.getState().setActiveChat(chatId);
  }

  clearActiveChat(): void {
    useChatStore.getState().setActiveChat(null);
  }
}

export const chatSessionActions = new ChatSessionActions();