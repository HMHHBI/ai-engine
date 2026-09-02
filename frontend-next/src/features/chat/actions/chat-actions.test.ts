import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  chatActions,
  type SendMessageOptions,
} from "./chat-actions";

import {
  chatStreamService,
  type ChatStreamEvent,
} from "@/features/chat/stream/chat-stream-service";

import { useChatStore } from "@/features/chat/store/chat-store";
import { ApiError } from "@/lib/errors/api-error";

const baseOptions: SendMessageOptions = {
  chatId: 1,
  prompt: "Hello AI",
  model: "gemini-2.5-flash",
  task: "general",
};

beforeEach(() => {
  useChatStore.getState().reset();

  vi.spyOn(
    chatStreamService,
    "stream",
  );
  vi.spyOn(
    chatStreamService,
    "abort",
  );

  useChatStore
    .getState()
    .setActiveChat(1);
});

afterEach(() => {
  chatActions.invalidate();
  vi.restoreAllMocks();
});

describe("chatActions", () => {
  it("creates a user message and an assistant placeholder", async () => {
    vi.spyOn(
      chatStreamService,
      "stream",
    ).mockImplementation(
      async (
        _payload,
        handlers,
      ) => {
        handlers?.onEvent?.({
          type: "streamStarted",
        });

        handlers?.onEvent?.({
          type: "chunkReceived",
          chunk: "Hello back",
        });

        handlers?.onEvent?.({
          type: "streamCompleted",
        });
      },
    );

    await chatActions.sendMessage(
      baseOptions,
    );

    const state = useChatStore.getState();

    const messages =
      state.messagesByChat[1];

    expect(messages).toHaveLength(2);

    expect(messages[0]).toMatchObject({
      role: "user",
      content: "Hello AI",
    });

    expect(messages[1]).toMatchObject({
      role: "ai",
      content: "Hello back",
    });

    expect(
      state.streamingStatusByChat[1],
    ).toBe("completed");
  });

  it("transitions streaming state correctly", async () => {
    vi.spyOn(
      chatStreamService,
      "stream",
    ).mockImplementation(
      async (
        _payload,
        handlers,
      ) => {
        handlers?.onEvent?.({
          type: "streamStarted",
        });

        expect(
          useChatStore.getState()
            .streamingStatusByChat[1],
        ).toBe("streaming");

        handlers?.onEvent?.({
          type: "chunkReceived",
          chunk: "chunk",
        });

        handlers?.onEvent?.({
          type: "streamCompleted",
        });
      },
    );

    await chatActions.sendMessage(
      baseOptions,
    );

    expect(
      useChatStore.getState()
        .streamingStatusByChat[1],
    ).toBe("completed");
  });

  it("handles typed stream errors", async () => {
    const error = new ApiError(
      "Provider unavailable",
      "PROVIDER_DOWN",
      502,
    );

    vi.spyOn(
      chatStreamService,
      "stream",
    ).mockImplementation(
      async (
        _payload,
        handlers,
      ) => {
        handlers?.onEvent?.({
          type: "streamStarted",
        });

        handlers?.onEvent?.({
          type: "streamFailed",
          error: new ApiError(
            "Provider unavailable",
            "PROVIDER_DOWN",
            502,
          ),
        });

        throw error;
      },
    );

    await expect(
      chatActions.sendMessage(
        baseOptions,
      ),
    ).rejects.toThrow(
      "Provider unavailable",
    );

    expect(
      useChatStore.getState()
        .streamingStatusByChat[1],
    ).toBe("error");
  });

  it("stops an active stream", () => {
    chatActions.stopStreaming();

    expect(
      chatStreamService.abort,
    ).toHaveBeenCalled();

    expect(
      useChatStore.getState()
        .streamingStatusByChat[1],
    ).toBe("cancelled");
  });

  it("switches chats and aborts the previous stream", () => {
    chatActions.switchChat(2);

    expect(
      chatStreamService.abort,
    ).toHaveBeenCalled();

    expect(
      useChatStore.getState()
        .activeChatId,
    ).toBe(2);
  });

  it("passes the backend-compatible payload to the stream service", async () => {
    const streamSpy = vi
      .spyOn(chatStreamService, "stream")
      .mockImplementation(
        async (
          _payload,
          handlers,
        ) => {
          handlers?.onEvent?.({
            type: "streamCompleted",
          });
        },
      );

    await chatActions.sendMessage({
      chatId: 42,
      prompt: "Explain RAG",
      model: "gemini-2.5-flash",
      task: "general",
      fileContext: "Document context",
      imageBase64: ["base64-data"],
      imageMime: ["image/png"],
    });

    expect(streamSpy).toHaveBeenCalledWith(
      {
        chat_id: 42,
        prompt: "Explain RAG",
        model: "gemini-2.5-flash",
        task: "general",
        file_context: "Document context",
        image_base64: ["base64-data"],
        image_mime: ["image/png"],
      },
      expect.objectContaining({
        onEvent: expect.any(Function),
      }),
    );
  });

  it("ignores stale events from a previous chat", async () => {
    let firstHandlers:
      | {
          onEvent?: (
            event: ChatStreamEvent,
          ) => void;
        }
      | undefined;

    let secondHandlers:
      | {
          onEvent?: (
            event: ChatStreamEvent,
          ) => void;
        }
      | undefined;

    vi.spyOn(
      chatStreamService,
      "stream",
    )
      .mockImplementationOnce(
        async (
          _payload,
          handlers,
        ) => {
          firstHandlers = handlers;

          handlers?.onEvent?.({
            type: "streamStarted",
          });

          await new Promise(() => undefined);
        },
      )
      .mockImplementationOnce(
        async (
          _payload,
          handlers,
        ) => {
          secondHandlers = handlers;

          handlers?.onEvent?.({
            type: "streamStarted",
          });

          handlers?.onEvent?.({
            type: "chunkReceived",
            chunk: "B response",
          });

          handlers?.onEvent?.({
            type: "streamCompleted",
          });
        },
      );

    const firstPromise = chatActions.sendMessage({
      ...baseOptions,
      chatId: 1,
    });

    await Promise.resolve();

    chatActions.switchChat(2);

    const secondPromise = chatActions.sendMessage({
      ...baseOptions,
      chatId: 2,
    });

    await secondPromise;

    firstHandlers?.onEvent?.({
      type: "chunkReceived",
      chunk: "STALE A DATA",
    });

    const state = useChatStore.getState();

    expect(
      state.messagesByChat[2]?.at(-1)?.content,
    ).toBe("B response");

    expect(
      state.messagesByChat[1]?.at(-1)?.content,
    ).not.toContain("STALE A DATA");

    expect(
      state.streamingStatusByChat[2],
    ).toBe("completed");

    expect(secondHandlers).toBeDefined();
    void firstPromise;
  });
});