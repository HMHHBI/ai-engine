import { ApiError } from "@/lib/errors/api-error";
import { chatApi } from "@/lib/api/chat";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { useDocumentStore } from "@/features/documents/document-store";
import type {
  AIModel,
  AIProvider,
  ChatMessage,
  StreamPayload,
} from "@/types/api";

export interface SendMessageOptions {
  chatId: number;
  prompt: string;
  model?: AIModel;
  provider?: AIProvider;
  imageBase64?: string[];
  imageMime?: string[];
}

export function buildStreamPayload(
  options: SendMessageOptions,
  selectedDocumentId: number | null,
): StreamPayload {
  const payload: StreamPayload = {
    chat_id: options.chatId,
    prompt: options.prompt.trim(),
    model: options.model,
    provider: options.provider,
    image_base64: options.imageBase64,
    image_mime: options.imageMime,
  };

  if (selectedDocumentId !== null) {
    payload.document_id = selectedDocumentId;
  }

  return payload;
}

class ChatActions {
  async sendMessage(options: SendMessageOptions): Promise<void> {
    const {
      chatId,
      prompt,
      model,
      provider,
      imageBase64,
      imageMime,
    } = options;

    const trimmedPrompt = prompt.trim();

    if (!trimmedPrompt) {
      throw new Error("Prompt cannot be empty.");
    }

    const requestId = chatRequestController.next();

    const isCurrentRequest = (): boolean =>
      chatRequestController.isCurrent(requestId);

    const hasChatState = (): boolean => {
      const chatStore = useChatStore.getState();
      const sessionStore = useChatSessionStore.getState();

      return (
        chatStore.messagesByChat[chatId] !== undefined ||
        chatStore.loadingChatIds[chatId] !== undefined ||
        chatStore.streamingStatusByChat[chatId] !== undefined ||
        chatStore.pdfStateByChat[chatId] !== undefined ||
        sessionStore.sessions.some((session) => session.id === chatId)
      );
    };

    const canMutateChat = (): boolean =>
      isCurrentRequest() && hasChatState();

    const store = useChatStore.getState();

    const session = useChatSessionStore
      .getState()
      .sessions.find((item) => item.id === chatId);

    const isFirstMessage = session?.title === "New Chat";

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: trimmedPrompt,
    };

    store.addMessage(chatId, userMessage);

    const aiMessage: ChatMessage = {
      id: Date.now() + 1,
      role: "ai",
      content: "",
    };

    store.addMessage(chatId, aiMessage);

    store.setStreamingStatus(chatId, "streaming");

    const selectedDocumentId =
    useDocumentStore.getState()
      .selectedDocumentIdByChat[chatId] ?? null;

    const payload = buildStreamPayload(
      {
        chatId,
        prompt: trimmedPrompt,
        model,
        provider,
        imageBase64,
        imageMime,
      },
      selectedDocumentId,
    );

    try {
      await chatStreamService.stream(payload, {
        onEvent: (event) => {
          if (!canMutateChat()) {
            return;
          }

          switch (event.type) {
            case "streamStarted":
              useChatStore.getState().setStreamingStatus(chatId, "streaming");

              if (isFirstMessage) {
                chatSessionActions.syncFirstMessageTitle(
                  chatId,
                  trimmedPrompt,
                );
              }
              break;

            case "sourcesReceived":
              useChatStore.getState().setMessageSources(chatId, event.sources);
              break;

            case "chunkReceived":
              if (event.chunk) {
                useChatStore
                  .getState()
                  .appendToLastMessage(chatId, event.chunk);
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
              throw event.error;
          }
        },
      });
    } catch (error) {
      if (!isCurrentRequest()) {
        return;
      }

      if (
        error instanceof ApiError &&
        error.code === "STREAM_ABORTED"
      ) {
        if (hasChatState()) {
          store.setStreamingStatus(chatId, "cancelled");
        }
        return;
      }

      if (hasChatState()) {
        store.setStreamingStatus(chatId, "error");
      }

      throw error;
    }
  }

  async uploadPdf(
    chatId: number,
    file: File,
  ): Promise<{
    filename: string;
    chunksCount: number;
  }> {
    const chatStore = useChatStore.getState();

    chatStore.setPdfState(chatId, {
      status: "uploading",
      filename: file.name,
      chunksCount: null,
      error: null,
    });

    try {
      chatStore.setPdfState(chatId, {
        status: "processing",
      });

      const response = await chatApi.uploadPdf(chatId, file);

      chatStore.setPdfState(chatId, {
        status: "ready",
        filename: response.filename,
        chunksCount: response.chunks_count,
        error: null,
      });

      useChatSessionStore.getState().updateSession(chatId, {
        has_pdf: true,
      });

      return {
        filename: response.filename,
        chunksCount: response.chunks_count,
      };
    } catch (error) {
      let message = "PDF upload failed.";

      if (error instanceof ApiError) {
        if (error.status === 413) {
          message = "This PDF is too large (max 20MB).";
        } else if (error.status === 429) {
          message = "Upload limit reached. Try again later.";
        } else if (error.status && error.status >= 500) {
          message = "AI processing service is temporarily unavailable.";
        } else {
          message = error.message;
        }
      } else if (error instanceof Error) {
        message = error.message;
      }

      chatStore.setPdfState(chatId, {
        status: "error",
        error: message,
      });

      throw new Error(message);
    }
  }

  stopStreaming(): void {
    chatRequestController.invalidate();
  }

  cancelForChat(chatId: number): void {
    chatRequestController.cancelChat(chatId);

    if (chatStreamService.currentChatId === chatId) {
      useChatStore.getState().setStreamingStatus(chatId, "cancelled");
    }
  }

  invalidate(): void {
    chatRequestController.invalidate();
  }
}

export const chatActions = new ChatActions();