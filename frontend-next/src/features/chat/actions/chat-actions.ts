import { ApiError } from "@/lib/errors/api-error";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import type { ChatMessage, StreamPayload } from "@/types/api";

export interface SendMessageOptions {
  chatId: number;
  prompt: string;
  imageBase64?: string[];
  imageMime?: string[];
}

class ChatActions {
  async sendMessage(options: SendMessageOptions): Promise<void> {
    const { chatId, prompt, imageBase64, imageMime } = options;
    const trimmedPrompt = prompt.trim();

    if (!trimmedPrompt) {
      throw new Error("Prompt cannot be empty.");
    }

    const store = useChatStore.getState();
    const session = useChatSessionStore
      .getState()
      .sessions.find((item) => item.id === chatId);

    const isFirstMessage = session?.title === "New Chat";

    // Optimistic user message
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: trimmedPrompt,
    };
    store.addMessage(chatId, userMessage);

    // Optimistic AI placeholder
    const aiMessage: ChatMessage = {
      id: Date.now() + 1,
      role: "ai",
      content: "",
    };
    store.addMessage(chatId, aiMessage);
    store.setStreamingStatus(chatId, "streaming");

    const payload: StreamPayload = {
      chat_id: chatId,
      prompt: trimmedPrompt,
      image_base64: imageBase64,
      image_mime: imageMime,
    };

    try {
      await chatStreamService.stream(payload, {
        onEvent: (event) => {
          switch (event.type) {
            case "streamStarted":
              useChatStore.getState().setStreamingStatus(chatId, "streaming");
              if (isFirstMessage) {
                chatSessionActions.syncFirstMessageTitle(chatId, trimmedPrompt);
              }
              break;

            case "chunkReceived":
              if (event.chunk) {
                useChatStore.getState().appendToLastMessage(chatId, event.chunk);
              }
              break;

            case "streamCompleted":
              useChatStore.getState().setStreamingStatus(chatId, "completed");
              break;

            case "streamCancelled":
              useChatStore.getState().setStreamingStatus(chatId, "cancelled");
              break;

            case "streamFailed":
              useChatStore.getState().setStreamingStatus(chatId, "error");
              break;
          }
        },
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "STREAM_ABORTED") {
        store.setStreamingStatus(chatId, "cancelled");
        return;
      }

      store.setStreamingStatus(chatId, "error");
      throw error;
    }
  }

  stopStreaming(): void {
    chatStreamService.abort();
  }
}

export const chatActions = new ChatActions();