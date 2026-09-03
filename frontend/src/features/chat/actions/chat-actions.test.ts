import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatActions } from "./chat-actions";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import type { ChatStreamHandlers } from "@/features/chat/stream/chat-stream-service";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { ApiError } from "@/lib/errors/api-error";
import type { StreamPayload } from "@/types/api";
import { chatApi } from "@/lib/api/chat";

vi.mock("@/features/chat/stream/chat-stream-service", () => ({
  chatStreamService: {
    stream: vi.fn(),
    abort: vi.fn(),
    abortChat: vi.fn(),
    currentChatId: null,
  },
}));

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    create: vi.fn(),
    getAll: vi.fn(),
    get: vi.fn(),
    updateTitle: vi.fn(),
    delete: vi.fn(),
    uploadPdf: vi.fn(),
  },
}));

describe("chatActions", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
    useChatSessionStore.getState().reset();
    chatRequestController.invalidate();
    vi.clearAllMocks();
    vi.mocked(chatStreamService.stream).mockReset();
    vi.mocked(chatStreamService.abort).mockReset();
    vi.mocked(chatStreamService.abortChat).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws error when prompt is empty", async () => {
    await expect(
      chatActions.sendMessage({
        chatId: 1,
        prompt: "   ",
      }),
    ).rejects.toThrow("Prompt cannot be empty.");
  });

  it("adds optimistic user and AI messages", async () => {
    vi.mocked(chatStreamService.stream).mockResolvedValue();

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Hello",
    });

    const messages = useChatStore.getState().messagesByChat[1];

    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("user");
    expect(messages[0].content).toBe("Hello");
    expect(messages[1].role).toBe("ai");
    expect(messages[1].content).toBe("");
  });

  it("updates message content on chunk event", async () => {
    vi.mocked(chatStreamService.stream).mockImplementation(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "chunkReceived", chunk: "World" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Hello",
    });

    const messages = useChatStore.getState().messagesByChat[1];

    expect(messages[1].content).toBe("World");
    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("completed");
  });

  it("attaches sources to the current AI message", async () => {
    const sources = [
      { id: 101, page_number: 3, chunk_index: 7, distance: 0.12 },
      { id: 102, page_number: 8, chunk_index: 15, distance: 0.24 },
    ];

    vi.mocked(chatStreamService.stream).mockImplementation(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "sourcesReceived", sources });
        handlers?.onEvent?.({ type: "chunkReceived", chunk: "Answer" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Question",
    });

    const messages = useChatStore.getState().messagesByChat[1];

    expect(messages).toHaveLength(2);
    expect(messages[1].role).toBe("ai");
    expect(messages[1].content).toBe("Answer");
    expect(messages[1].sources).toEqual(sources);
  });

  it("sets cancelled status when stream is aborted", async () => {
    vi.mocked(chatStreamService.stream).mockRejectedValue(
      new ApiError("Aborted", "STREAM_ABORTED", 499),
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Hello",
    });

    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("cancelled");
  });

  it("sets error status on network failures", async () => {
    vi.mocked(chatStreamService.stream).mockRejectedValue(
      new Error("Network disconnect"),
    );

    await expect(
      chatActions.sendMessage({
        chatId: 1,
        prompt: "Hello",
      }),
    ).rejects.toThrow("Network disconnect");

    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("error");
  });

  it("delegates cancellation to chatRequestController and streamService", () => {
    chatActions.stopStreaming();
    expect(chatStreamService.abort).toHaveBeenCalled();
  });

  describe("chat switching during streaming", () => {
    it("blocks late chunks after switching from chat A to chat B", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Question A",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Answer B" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 2,
        prompt: "Question B",
      });

      firstHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE A CHUNK",
      });

      await firstRequest;

      expect(useChatStore.getState().messagesByChat[1][1].content).toBe("");
      expect(useChatStore.getState().messagesByChat[2][1].content).toBe("Answer B");
    });

    it("blocks late sources after switching from chat A to chat B", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      const staleSources = [
        { id: 900, page_number: 99, chunk_index: 999, distance: 0.01 },
      ];

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Partial A" });
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Question A",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({
            type: "sourcesReceived",
            sources: [{ id: 200, page_number: 2, chunk_index: 4, distance: 0.2 }],
          });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Answer B" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 2,
        prompt: "Question B",
      });

      firstHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: staleSources,
      });

      await firstRequest;

      const chatA = useChatStore.getState().messagesByChat[1];
      const chatB = useChatStore.getState().messagesByChat[2];

      expect(chatA[1].sources).toBeUndefined();
      expect(chatB[1].sources).toEqual([
        { id: 200, page_number: 2, chunk_index: 4, distance: 0.2 },
      ]);
      expect(chatB[1].sources).not.toEqual(staleSources);
    });

    it("blocks late completion after switching chats", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Question A",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 2,
        prompt: "Question B",
      });

      expect(useChatStore.getState().streamingStatusByChat[2]).toBe("completed");

      firstHandlers?.onEvent?.({ type: "streamCompleted" });

      await firstRequest;

      expect(useChatStore.getState().streamingStatusByChat[2]).toBe("completed");
      expect(useChatStore.getState().streamingStatusByChat[1]).toBe("streaming");
    });

    it("blocks late errors after switching chats", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Question A",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Answer B" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 2,
        prompt: "Question B",
      });

      firstHandlers?.onEvent?.({
        type: "streamFailed",
        error: new ApiError("STALE A ERROR", "STREAM_ERROR"),
      });

      await firstRequest;

      expect(useChatStore.getState().streamingStatusByChat[2]).toBe("completed");
      expect(useChatStore.getState().messagesByChat[2][1].content).toBe("Answer B");
    });

    it("keeps stale events isolated when switching A -> B -> A", async () => {
      let firstAHandlers: ChatStreamHandlers | undefined;
      let secondAHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstAHandlers = handlers;
        },
      );

      const firstARequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "First A",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Answer B" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 2,
        prompt: "Question B",
      });

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          secondAHandlers = handlers;
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Current A" });
        },
      );

      const secondARequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Second A",
      });

      firstAHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE ORIGINAL A",
      });

      firstAHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 999, page_number: 99, chunk_index: 99, distance: 0.99 }],
      });

      firstAHandlers?.onEvent?.({ type: "streamCompleted" });

      secondAHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: " answer",
      });

      secondAHandlers?.onEvent?.({ type: "streamCompleted" });

      await Promise.all([firstARequest, secondARequest]);

      const messages = useChatStore.getState().messagesByChat[1];

      expect(messages).toHaveLength(4);
      expect(messages[1].content).toBe("");
      expect(messages[1].sources).toBeUndefined();
      expect(messages[3].content).toBe("Current A answer");
    });
  });

  describe("retry lifecycle", () => {
    it("prevents late events from a failed attempt from mutating a retry", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({
            type: "sourcesReceived",
            sources: [{ id: 101, page_number: 1, chunk_index: 1, distance: 0.1 }],
          });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Old partial" });
          handlers?.onEvent?.({
            type: "streamFailed",
            error: new ApiError("First attempt failed", "STREAM_ERROR"),
          });
        },
      );

      await expect(
        chatActions.sendMessage({
          chatId: 1,
          prompt: "Retry me",
        }),
      ).rejects.toThrow("First attempt failed");

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({
            type: "sourcesReceived",
            sources: [{ id: 202, page_number: 2, chunk_index: 2, distance: 0.2 }],
          });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "New answer" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      const retryRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Retry me",
      });

      firstHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 999, page_number: 99, chunk_index: 99, distance: 0.99 }],
      });

      firstHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE RETRY CONTENT",
      });

      firstHandlers?.onEvent?.({
        type: "streamFailed",
        error: new ApiError("STALE RETRY ERROR", "STREAM_ERROR"),
      });

      await retryRequest;

      const messages = useChatStore.getState().messagesByChat[1];
      const latestMessage = messages[messages.length - 1];

      expect(latestMessage.role).toBe("ai");
      expect(latestMessage.content).toBe("New answer");
      expect(latestMessage.sources).toEqual([
        { id: 202, page_number: 2, chunk_index: 2, distance: 0.2 },
      ]);
      expect(latestMessage.sources).not.toContainEqual(
        expect.objectContaining({ id: 999 }),
      );
      expect(useChatStore.getState().streamingStatusByChat[1]).toBe("completed");
    });

    it("replaces old sources with retry sources instead of merging them", async () => {
      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({
            type: "sourcesReceived",
            sources: [
              { id: 10, page_number: 1, chunk_index: 1, distance: 0.1 },
              { id: 11, page_number: 2, chunk_index: 2, distance: 0.2 },
            ],
          });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Old answer" });
          handlers?.onEvent?.({
            type: "streamFailed",
            error: new ApiError("Failed", "STREAM_ERROR"),
          });
        },
      );

      await expect(
        chatActions.sendMessage({
          chatId: 1,
          prompt: "Question",
        }),
      ).rejects.toThrow("Failed");

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({
            type: "sourcesReceived",
            sources: [{ id: 20, page_number: 5, chunk_index: 5, distance: 0.05 }],
          });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Retry answer" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      await chatActions.sendMessage({
        chatId: 1,
        prompt: "Question",
      });

      const messages = useChatStore.getState().messagesByChat[1];
      const retryMessage = messages[messages.length - 1];

      expect(retryMessage.sources).toEqual([
        { id: 20, page_number: 5, chunk_index: 5, distance: 0.05 },
      ]);
      expect(retryMessage.sources).not.toContainEqual(
        expect.objectContaining({ id: 10 }),
      );
      expect(retryMessage.sources).not.toContainEqual(
        expect.objectContaining({ id: 11 }),
      );
    });

    it("does not duplicate the original message when retrying", async () => {
      vi.mocked(chatStreamService.stream)
        .mockImplementationOnce(
          async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
            handlers?.onEvent?.({ type: "streamStarted" });
            handlers?.onEvent?.({ type: "chunkReceived", chunk: "Failed response" });
            handlers?.onEvent?.({
              type: "streamFailed",
              error: new ApiError("Temporary failure", "STREAM_ERROR"),
            });
          },
        )
        .mockImplementationOnce(
          async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
            handlers?.onEvent?.({ type: "streamStarted" });
            handlers?.onEvent?.({ type: "chunkReceived", chunk: "Successful retry" });
            handlers?.onEvent?.({ type: "streamCompleted" });
          },
        );

      await expect(
        chatActions.sendMessage({
          chatId: 1,
          prompt: "Same question",
        }),
      ).rejects.toThrow("Temporary failure");

      const existingMessages = useChatStore.getState().messagesByChat[1] ?? [];
      const userPrompt =
        existingMessages.find((m) => m.role === "user")?.content ??
        "Same question";

      await chatActions.sendMessage({
        chatId: 1,
        prompt: userPrompt,
      });

      const messages = useChatStore.getState().messagesByChat[1];
      expect(messages.length).toBeGreaterThanOrEqual(2);
      expect(messages[messages.length - 1].content).toBe("Successful retry");
    });
  });

  describe("abort and cancellation races", () => {
    it("ignores events from a stream after stopStreaming", async () => {
      let handlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementation(
        async (_payload: StreamPayload, streamHandlers?: ChatStreamHandlers) => {
          handlers = streamHandlers;
        },
      );

      const request = chatActions.sendMessage({
        chatId: 1,
        prompt: "Cancel me",
      });

      chatActions.stopStreaming();

      handlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE AFTER CANCEL",
      });

      handlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 999, page_number: 99, chunk_index: 99, distance: 0.99 }],
      });

      handlers?.onEvent?.({ type: "streamCompleted" });

      await request;

      const messages = useChatStore.getState().messagesByChat[1];

      expect(messages[1].content).toBe("");
      expect(messages[1].sources).toBeUndefined();
    });

    it("cancelForChat only cancels the matching active chat", () => {
      chatActions.cancelForChat(1);
      expect(chatStreamService.abort).not.toHaveBeenCalled();
      expect(useChatStore.getState().streamingStatusByChat[1]).toBeUndefined();
    });

    it("cancelForChat marks the active chat as cancelled", async () => {
      vi.mocked(chatStreamService.stream).mockImplementation(
        async () => undefined,
      );

      vi.spyOn(chatStreamService, "currentChatId", "get").mockReturnValue(1);

      const request = chatActions.sendMessage({
        chatId: 1,
        prompt: "Cancel active chat",
      });

      chatActions.cancelForChat(1);

      await request;

      expect(useChatStore.getState().streamingStatusByChat[1]).toBe("cancelled");
    });

    it("discards late events from a cancelled request before a retry", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Cancel and retry",
      });

      chatActions.stopStreaming();

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          handlers?.onEvent?.({ type: "streamStarted" });
          handlers?.onEvent?.({ type: "chunkReceived", chunk: "Retry result" });
          handlers?.onEvent?.({ type: "streamCompleted" });
        },
      );

      const retryRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Cancel and retry",
      });

      firstHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE CANCELLED RESULT",
      });

      firstHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 777, page_number: 77, chunk_index: 77, distance: 0.77 }],
      });

      firstHandlers?.onEvent?.({ type: "streamCompleted" });

      await Promise.all([firstRequest, retryRequest]);

      const messages = useChatStore.getState().messagesByChat[1];
      expect(messages[messages.length - 1].content).toBe("Retry result");
    });
  });

  describe("new chat and delete while streaming", () => {
    it("does not allow a late stream event from chat A to mutate newly created chat B", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Streaming A",
      });

      vi.mocked(chatApi.create).mockResolvedValue({
        chat_id: 2,
        title: "New Chat",
      } as never);

      const createdId = await chatSessionActions.createChat();

      firstHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE A",
      });

      firstHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 123, page_number: 12, chunk_index: 12, distance: 0.12 }],
      });

      await firstRequest;

      expect(createdId).toBe(2);
      expect(useChatStore.getState().messagesByChat[2] ?? []).toEqual([]);
    });

    it("does not resurrect deleted chat state from late stream events", async () => {
      let firstHandlers: ChatStreamHandlers | undefined;

      vi.mocked(chatStreamService.stream).mockImplementationOnce(
        async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
          firstHandlers = handlers;
        },
      );

      const firstRequest = chatActions.sendMessage({
        chatId: 1,
        prompt: "Delete while streaming",
      });

      vi.mocked(chatApi.delete).mockResolvedValue({
        message: "Chat deleted",
      } as never);

      await chatSessionActions.deleteChat(1);

      firstHandlers?.onEvent?.({
        type: "chunkReceived",
        chunk: "STALE AFTER DELETE",
      });

      firstHandlers?.onEvent?.({
        type: "sourcesReceived",
        sources: [{ id: 456, page_number: 45, chunk_index: 45, distance: 0.45 }],
      });

      firstHandlers?.onEvent?.({ type: "streamCompleted" });

      await firstRequest;

      expect(useChatStore.getState().messagesByChat[1]).toBeUndefined();
      expect(useChatStore.getState().streamingStatusByChat[1]).toBeUndefined();
    });
  });

  it("syncs the first message into the chat session title", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 1,
          user_id: 1,
          title: "New Chat",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
      ],
    });

    vi.mocked(chatStreamService.stream).mockImplementation(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Explain vector databases",
    });

    expect(useChatSessionStore.getState().sessions[0].title).toBe(
      "Explain vector databases",
    );
  });

  it("uses the backend-compatible 25-character title limit", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 1,
          user_id: 1,
          title: "New Chat",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
      ],
    });

    vi.mocked(chatStreamService.stream).mockImplementation(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Explain how retrieval augmented generation works",
    });

    expect(useChatSessionStore.getState().sessions[0].title).toBe(
      "Explain how retrieval aug...",
    );
  });

  it("promotes the first-message chat to the top of history", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 2,
          user_id: 1,
          title: "Older Chat",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
        {
          id: 1,
          user_id: 1,
          title: "New Chat",
          created_at: "2026-01-02T00:00:00Z",
          updated_at: "2026-01-02T10:00:00Z",
          has_pdf: false,
        },
      ],
    });

    vi.mocked(chatStreamService.stream).mockImplementation(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Hello AI Engine",
    });

    expect(
      useChatSessionStore.getState().sessions.map((session) => session.id),
    ).toEqual([1, 2]);
  });

  it("submits multimodal image payloads with strict index pairing", async () => {
    vi.mocked(chatStreamService.stream).mockResolvedValue();

    const testImages = ["base64-data-1", "base64-data-2"];
    const testMimes = ["image/png", "image/jpeg"];

    await chatActions.sendMessage({
      chatId: 1,
      prompt: "Describe these images",
      imageBase64: testImages,
      imageMime: testMimes,
    });

    expect(chatStreamService.stream).toHaveBeenCalledWith(
      expect.objectContaining({
        chat_id: 1,
        prompt: "Describe these images",
        image_base64: testImages,
        image_mime: testMimes,
      }),
      expect.anything(),
    );
  });
});