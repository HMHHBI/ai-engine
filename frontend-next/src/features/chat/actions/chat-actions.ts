import { ApiError } from "@/lib/errors/api-error";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import { useChatStore } from "@/features/chat/store/chat-store";
import type {
  ChatMessage,
  StreamPayload,
} from "@/types/api";

export interface SendMessageOptions {
  chatId: number;
  prompt: string;
  model?: StreamPayload["model"];
  provider?: StreamPayload["provider"];
  task?: StreamPayload["task"];
  fileContext?: string;
  imageBase64?: string[];
  imageMime?: string[];
}

class ChatActions {
  private generation = 0;

  async sendMessage(options: SendMessageOptions): Promise<void> {
    const {
      chatId,
      prompt,
      model,
      provider,
      task = "general",
      fileContext,
      imageBase64,
      imageMime,
    } = options;

    const trimmedPrompt = prompt.trim();

    if (!trimmedPrompt) {
      return;
    }

    const requestGeneration = ++this.generation;

    const store = useChatStore.getState();

    const userMessage: ChatMessage = {
      chat_id: chatId,
      role: "user",
      content: trimmedPrompt,
    };

    const assistantMessage: ChatMessage = {
      chat_id: chatId,
      role: "ai",
      content: "",
    };

    store.addMessage(chatId, userMessage);
    store.addMessage(chatId, assistantMessage);
    store.setStreamingStatus(chatId, "streaming");

    const payload: StreamPayload = {
      chat_id: chatId,
      prompt: trimmedPrompt,
      task,
      model,
      provider,
      ...(fileContext?.trim()
        ? {
            file_context: fileContext,
          }
        : {}),
      ...(imageBase64?.length
        ? {
            image_base64: imageBase64,
          }
        : {}),
      ...(imageMime?.length
        ? {
            image_mime: imageMime,
          }
        : {}),
    };

    try {
      await chatStreamService.stream(payload, {
        onEvent: (event) => {
          if (requestGeneration !== this.generation) {
            return;
          }

          switch (event.type) {
            case "streamStarted":
              useChatStore
                .getState()
                .setStreamingStatus(chatId, "streaming");
              break;

            case "chunkReceived":
              useChatStore
                .getState()
                .appendToLastMessage(
                  chatId,
                  event.chunk,
                );
              break;

            case "streamCompleted":
              useChatStore
                .getState()
                .setStreamingStatus(
                  chatId,
                  "completed",
                );
              break;

            case "streamCancelled":
              useChatStore
                .getState()
                .setStreamingStatus(
                  chatId,
                  "cancelled",
                );
              break;

            case "streamFailed":
              useChatStore
                .getState()
                .setStreamingStatus(
                  chatId,
                  "error",
                );
              break;
          }
        },
      });
    } catch (error) {
      if (requestGeneration !== this.generation) {
        return;
      }

      if (
        error instanceof ApiError &&
        error.code === "STREAM_ABORTED"
      ) {
        useChatStore
          .getState()
          .setStreamingStatus(
            chatId,
            "cancelled",
          );

        return;
      }

      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        useChatStore
          .getState()
          .setStreamingStatus(
            chatId,
            "cancelled",
          );

        return;
      }

      useChatStore
        .getState()
        .setStreamingStatus(chatId, "error");

      throw error;
    }
  }

  stopStreaming(): void {
    this.generation += 1;

    chatStreamService.abort();

    const activeChatId =
      useChatStore.getState().activeChatId;

    if (activeChatId !== null) {
      useChatStore
        .getState()
        .setStreamingStatus(
          activeChatId,
          "cancelled",
        );
    }
  }

  switchChat(chatId: number | null): void {
    this.generation += 1;

    chatStreamService.abort();

    useChatStore
      .getState()
      .setActiveChat(chatId);
  }

  invalidate(): void {
    this.generation += 1;
  }
}

export const chatActions = new ChatActions();