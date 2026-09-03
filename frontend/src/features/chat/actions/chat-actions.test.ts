import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatActions } from "./chat-actions";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import type { ChatStreamHandlers } from "@/features/chat/stream/chat-stream-service";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { ApiError } from "@/lib/errors/api-error";
import type { StreamPayload } from "@/types/api";

vi.mock("@/features/chat/stream/chat-stream-service", () => ({
  chatStreamService: {
    stream: vi.fn(),
    abort: vi.fn(),
    abortChat: vi.fn(),
    currentChatId: null,
  },
}));

describe("chatActions", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
    useChatSessionStore.getState().reset();
    chatRequestController.invalidate();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws error when prompt is empty", async () => {
    await expect(
      chatActions.sendMessage({ chatId: 1, prompt: "   " }),
    ).rejects.toThrow("Prompt cannot be empty.");
  });

  it("adds optimistic user and AI messages", async () => {
    vi.mocked(chatStreamService.stream).mockResolvedValue();

    await chatActions.sendMessage({ chatId: 1, prompt: "Hello" });

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

    await chatActions.sendMessage({ chatId: 1, prompt: "Hello" });

    const messages = useChatStore.getState().messagesByChat[1];
    expect(messages[1].content).toBe("World");
    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("completed");
  });

  it("sets cancelled status when stream is aborted", async () => {
    vi.mocked(chatStreamService.stream).mockRejectedValue(
      new ApiError("Aborted", "STREAM_ABORTED", 499),
    );

    await chatActions.sendMessage({ chatId: 1, prompt: "Hello" });

    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("cancelled");
  });

  it("sets error status on network failures", async () => {
    vi.mocked(chatStreamService.stream).mockRejectedValue(
      new Error("Network disconnect"),
    );

    await expect(
      chatActions.sendMessage({ chatId: 1, prompt: "Hello" }),
    ).rejects.toThrow("Network disconnect");

    expect(useChatStore.getState().streamingStatusByChat[1]).toBe("error");
  });

  it("delegates cancellation to chatRequestController and streamService", () => {
    chatActions.stopStreaming();
    expect(chatStreamService.abort).toHaveBeenCalled();
  });

  it("discards chunks from previous streams when a new request starts", async () => {
    let capturedHandler1: ChatStreamHandlers | undefined;

    vi.mocked(chatStreamService.stream).mockImplementationOnce(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        capturedHandler1 = handlers;
      },
    );

    const firstMsg = chatActions.sendMessage({ chatId: 1, prompt: "First" });

    vi.mocked(chatStreamService.stream).mockImplementationOnce(
      async (_payload: StreamPayload, handlers?: ChatStreamHandlers) => {
        handlers?.onEvent?.({ type: "streamStarted" });
        handlers?.onEvent?.({ type: "chunkReceived", chunk: "Second result" });
        handlers?.onEvent?.({ type: "streamCompleted" });
      },
    );

    await chatActions.sendMessage({ chatId: 2, prompt: "Second" });

    // Late chunk from first request arrives
    capturedHandler1?.onEvent?.({
      type: "chunkReceived",
      chunk: "Stale chunk from first",
    });

    await firstMsg;

    const chat1Messages = useChatStore.getState().messagesByChat[1];
    const chat2Messages = useChatStore.getState().messagesByChat[2];

    expect(chat1Messages[1].content).toBe("");
    expect(chat2Messages[1].content).toBe("Second result");
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