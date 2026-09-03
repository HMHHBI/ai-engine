import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  chatStreamService,
} from "./chat-stream-service";

function createSseEvent(
  event: string,
  data: unknown,
): string {
  return [
    `event: ${event}`,
    `data: ${JSON.stringify(data)}`,
    "",
    "",
  ].join("\n");
}

function createResponseStream(
  chunks: string[],
): ReadableStream<Uint8Array> {
  const encoder =
    new TextEncoder();

  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(
          encoder.encode(chunk),
        );
      }

      controller.close();
    },
  });
}

describe("chatStreamService", () => {
  const originalFetch =
    global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL =
      "http://localhost:8000";

    chatStreamService.abort();

    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch =
      originalFetch;

    chatStreamService.abort();
  });

  it("parses the complete SSE streaming contract", async () => {
    const stream = createResponseStream([
      createSseEvent(
        "stream_started",
        {
          provider: "gemini",
          model: "gemini-2.5-flash",
        },
      ),
      createSseEvent(
        "sources",
        {
          sources: [
            {
              id: 101,
              page_number: 3,
              chunk_index: 7,
              distance: 0.142,
            },
            {
              id: 102,
              page_number: 4,
              chunk_index: 8,
              distance: 0.219,
            },
          ],
        },
      ),
      createSseEvent(
        "chunk",
        {
          text: "Hello ",
        },
      ),
      createSseEvent(
        "chunk",
        {
          text: "world!",
        },
      ),
      createSseEvent(
        "stream_completed",
        {
          message_id: 55,
        },
      ),
    ]);

    global.fetch =
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({
          "content-type":
            "text/event-stream",
        }),
      });

    const events: string[] = [];
    const chunks: string[] = [];
    const sources: unknown[] = [];

    let startedProvider:
      | string
      | undefined;

    let startedModel:
      | string
      | undefined;

    let completedMessageId:
      | number
      | undefined;

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
        provider: "gemini",
        model: "gemini-2.5-flash",
      },
      {
        onEvent: (event) => {
          events.push(
            event.type,
          );

          if (
            event.type ===
            "streamStarted"
          ) {
            startedProvider =
              event.provider;

            startedModel =
              event.model;
          }

          if (
            event.type ===
            "sourcesReceived"
          ) {
            sources.push(
              ...event.sources,
            );
          }

          if (
            event.type ===
            "chunkReceived"
          ) {
            chunks.push(
              event.chunk,
            );
          }

          if (
            event.type ===
            "streamCompleted"
          ) {
            completedMessageId =
              event.messageId;
          }
        },
      },
    );

    expect(events).toEqual([
      "streamStarted",
      "sourcesReceived",
      "chunkReceived",
      "chunkReceived",
      "streamCompleted",
    ]);

    expect(
      startedProvider,
    ).toBe("gemini");

    expect(
      startedModel,
    ).toBe(
      "gemini-2.5-flash",
    );

    expect(chunks).toEqual([
      "Hello ",
      "world!",
    ]);

    expect(sources).toEqual([
      {
        id: 101,
        page_number: 3,
        chunk_index: 7,
        distance: 0.142,
      },
      {
        id: 102,
        page_number: 4,
        chunk_index: 8,
        distance: 0.219,
      },
    ]);

    expect(
      completedMessageId,
    ).toBe(55);

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);
  });

  it("parses SSE correctly when events are split across network chunks", async () => {
    const completeEvent =
      createSseEvent(
        "chunk",
        {
          text: "Hello ",
        },
      );

    const completeEvent2 =
      createSseEvent(
        "chunk",
        {
          text: "world!",
        },
      );

    const startedEvent =
      createSseEvent(
        "stream_started",
        {
          provider: "ollama",
          model: "llama3.2",
        },
      );

    const completedEvent =
      createSseEvent(
        "stream_completed",
        {
          message_id: 99,
        },
      );

    const combined =
      startedEvent +
      completeEvent +
      completeEvent2 +
      completedEvent;

    const splitPoints = [
      5,
      17,
      31,
      46,
      63,
    ];

    const chunks: string[] = [];

    let cursor = 0;

    for (
      const point of splitPoints
    ) {
      if (
        point <= cursor ||
        point >= combined.length
      ) {
        continue;
      }

      chunks.push(
        combined.slice(
          cursor,
          point,
        ),
      );

      cursor = point;
    }

    chunks.push(
      combined.slice(cursor),
    );

    global.fetch =
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body:
          createResponseStream(
            chunks,
          ),
        headers: new Headers({
          "content-type":
            "text/event-stream",
        }),
      });

    const receivedChunks: string[] =
      [];

    let completed = false;

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          if (
            event.type ===
            "chunkReceived"
          ) {
            receivedChunks.push(
              event.chunk,
            );
          }

          if (
            event.type ===
            "streamCompleted"
          ) {
            completed = true;
          }
        },
      },
    );

    expect(
      receivedChunks,
    ).toEqual([
      "Hello ",
      "world!",
    ]);

    expect(completed).toBe(true);
  });

  it("handles stream_error as streamFailed", async () => {
    const stream =
      createResponseStream([
        createSseEvent(
          "stream_started",
          {
            provider: "openai",
            model: "gpt-4o-mini",
          },
        ),
        createSseEvent(
          "stream_error",
          {
            code:
              "provider_unavailable",
            message:
              "The AI provider is temporarily unavailable. Please try again.",
          },
        ),
      ]);

    global.fetch =
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({
          "content-type":
            "text/event-stream",
        }),
      });

    let failedError:
      | Error
      | undefined;

    await expect(
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "test",
        },
        {
          onEvent: (event) => {
            if (
              event.type ===
              "streamFailed"
            ) {
              failedError =
                event.error;
            }
          },
        },
      ),
    ).resolves.toBeUndefined();

    expect(
      failedError,
    ).toBeDefined();

    expect(
      failedError?.message,
    ).toBe(
      "The AI provider is temporarily unavailable. Please try again.",
    );
  });

  it("handles explicit stream cancellation event", async () => {
    const stream =
      createResponseStream([
        createSseEvent(
          "stream_started",
          {
            provider: "ollama",
            model: "llama3.2",
          },
        ),
        createSseEvent(
          "stream_cancelled",
          {
            message:
              "The stream was cancelled.",
          },
        ),
      ]);

    global.fetch =
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({
          "content-type":
            "text/event-stream",
        }),
      });

    let cancelled = false;
    let cancellationMessage:
      | string
      | undefined;

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          if (
            event.type ===
            "streamCancelled"
          ) {
            cancelled = true;
            cancellationMessage =
              event.message;
          }
        },
      },
    );

    expect(cancelled).toBe(true);

    expect(
      cancellationMessage,
    ).toBe(
      "The stream was cancelled.",
    );
  });

  it("handles abort gracefully and marks stream cancelled", async () => {
    global.fetch =
      vi.fn().mockImplementation(
        (
          _url,
          init?: RequestInit,
        ) => {
          return new Promise(
            (_resolve, reject) => {
              const signal =
                init?.signal;

              if (
                signal?.aborted
              ) {
                reject(
                  new DOMException(
                    "The user aborted a request.",
                    "AbortError",
                  ),
                );

                return;
              }

              signal?.addEventListener(
                "abort",
                () => {
                  reject(
                    new DOMException(
                      "The user aborted a request.",
                      "AbortError",
                    ),
                  );
                },
              );
            },
          );
        },
      );

    let cancelled = false;

    const streamPromise =
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "test",
        },
        {
          onEvent: (event) => {
            if (
              event.type ===
              "streamCancelled"
            ) {
              cancelled = true;
            }
          },
        },
      );

    chatStreamService.abort();

    await expect(
      streamPromise,
    ).rejects.toThrow(
      "The AI stream was cancelled.",
    );

    expect(
      cancelled,
    ).toBe(true);

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);
  });

  it("aborts active stream when a new stream starts", async () => {
    global.fetch =
      vi.fn().mockImplementation(
        (
          _url,
          init?: RequestInit,
        ) => {
          return new Promise(
            (_resolve, reject) => {
              const signal =
                init?.signal;

              if (
                signal?.aborted
              ) {
                reject(
                  new DOMException(
                    "The user aborted a request.",
                    "AbortError",
                  ),
                );

                return;
              }

              signal?.addEventListener(
                "abort",
                () => {
                  reject(
                    new DOMException(
                      "The user aborted a request.",
                      "AbortError",
                    ),
                  );
                },
              );
            },
          );
        },
      );

    const stream1 =
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "first",
        },
        {},
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(1);

    const stream2 =
      chatStreamService.stream(
        {
          chat_id: 2,
          prompt: "second",
        },
        {},
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(2);

    await expect(
      stream1,
    ).rejects.toThrow(
      "The AI stream was cancelled.",
    );

    chatStreamService.abort();

    await expect(
      stream2,
    ).rejects.toThrow(
      "The AI stream was cancelled.",
    );
  });
});