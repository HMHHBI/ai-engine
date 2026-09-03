import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  ChatStreamService,
  chatStreamService,
} from "./chat-stream-service";
import type { ChatStreamEvent } from "./chat-stream-service";

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
  const encoder = new TextEncoder();

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

function createResponse(
  body: ReadableStream<Uint8Array> | null,
  status = 200,
  headers: Record<string, string> = {
    "content-type": "text/event-stream",
  },
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    body,
    headers: new Headers(headers),
  } as Response;
}

function createDeferredStream() {
  const encoder = new TextEncoder();

  let streamController:
    | ReadableStreamDefaultController<Uint8Array>
    | undefined;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
    },
  });

  return {
    stream,

    enqueue(value: string): void {
      streamController?.enqueue(
        encoder.encode(value),
      );
    },

    close(): void {
      streamController?.close();
    },
  };
}

function collectEvents(): {
  events: ChatStreamEvent[];
  onEvent: (event: ChatStreamEvent) => void;
} {
  const events: ChatStreamEvent[] = [];

  return {
    events,
    onEvent: (event) => {
      events.push(event);
    },
  };
}

describe("chatStreamService", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL =
      "http://localhost:8000";

    chatStreamService.abort();

    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;

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

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const {
      events,
      onEvent,
    } = collectEvents();

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
        provider: "gemini",
        model: "gemini-2.5-flash",
      },
      { onEvent },
    );

    expect(
      events.map((event) => event.type),
    ).toEqual([
      "streamStarted",
      "sourcesReceived",
      "chunkReceived",
      "chunkReceived",
      "streamCompleted",
    ]);

    const started = events[0];

    expect(started).toMatchObject({
      type: "streamStarted",
      provider: "gemini",
      model: "gemini-2.5-flash",
    });

    const sourceEvent = events[1];

    expect(sourceEvent).toMatchObject({
      type: "sourcesReceived",
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
    });

    expect(
      events
        .filter(
          (event) =>
            event.type ===
            "chunkReceived",
        )
        .map(
          (event) =>
            event.type ===
            "chunkReceived"
              ? event.chunk
              : "",
        ),
    ).toEqual([
      "Hello ",
      "world!",
    ]);

    expect(
      events.find(
        (event) =>
          event.type ===
          "streamCompleted",
      ),
    ).toMatchObject({
      type: "streamCompleted",
      messageId: 55,
    });

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("parses SSE correctly when events are split across network chunks", async () => {
    const combined = [
      createSseEvent(
        "stream_started",
        {
          provider: "ollama",
          model: "llama3.2",
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
          message_id: 99,
        },
      ),
    ].join("");

    const chunks: string[] = [];

    for (
      let index = 0;
      index < combined.length;
      index += 7
    ) {
      chunks.push(
        combined.slice(
          index,
          index + 7,
        ),
      );
    }

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(
          createResponseStream(chunks),
        ),
      );

    const receivedChunks: string[] = [];
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

  it("handles CRLF SSE framing", async () => {
    const stream = createResponseStream([
      [
        "event: chunk",
        'data: {"text":"CRLF works"}',
        "",
        "",
      ].join("\r\n"),
      [
        "event: stream_completed",
        'data: {"message_id":123}',
        "",
        "",
      ].join("\r\n"),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const events: ChatStreamEvent[] = [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(events).toEqual([
      {
        type: "chunkReceived",
        chunk: "CRLF works",
      },
      {
        type: "streamCompleted",
        messageId: 123,
      },
    ]);
  });

  it("ignores SSE comment and heartbeat lines", async () => {
    const stream = createResponseStream([
      [
        ": heartbeat",
        "",
        "event: chunk",
        'data: {"text":"Hello"}',
        "",
        "",
      ].join("\n"),
      [
        ": another heartbeat",
        "",
        "event: stream_completed",
        "data: {}",
        "",
        "",
      ].join("\n"),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const events: ChatStreamEvent[] = [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(events).toEqual([
      {
        type: "chunkReceived",
        chunk: "Hello",
      },
      {
        type: "streamCompleted",
        messageId: undefined,
      },
    ]);
  });

  it("does not emit duplicate completion after an explicit completion event", async () => {
    const stream = createResponseStream([
      createSseEvent(
        "stream_completed",
        {
          message_id: 77,
        },
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const completedEvents: ChatStreamEvent[] =
      [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          if (
            event.type ===
            "streamCompleted"
          ) {
            completedEvents.push(event);
          }
        },
      },
    );

    expect(
      completedEvents,
    ).toHaveLength(1);

    expect(
      completedEvents[0],
    ).toMatchObject({
      type: "streamCompleted",
      messageId: 77,
    });
  });

  it("emits streamCompleted when the server closes cleanly without an explicit completion event", async () => {
    const stream = createResponseStream([
      createSseEvent(
        "chunk",
        {
          text: "final answer",
        },
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const events: ChatStreamEvent[] = [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(events).toEqual([
      {
        type: "chunkReceived",
        chunk: "final answer",
      },
      {
        type: "streamCompleted",
        messageId: undefined,
      },
    ]);
  });

  it("handles stream_error as streamFailed with the backend error contract", async () => {
    const stream = createResponseStream([
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
          code: "provider_unavailable",
          message:
            "The AI provider is temporarily unavailable. Please try again.",
        },
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

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
              failedError = event.error;
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

  it("rejects transport failures and emits streamFailed", async () => {
    const transportError =
      new TypeError(
        "Failed to fetch",
      );

    global.fetch = vi
      .fn()
      .mockRejectedValue(
        transportError,
      );

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
              failedError = event.error;
            }
          },
        },
      ),
    ).rejects.toThrow(
      "The AI stream failed.",
    );

    expect(
      failedError,
    ).toBeDefined();

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("maps HTTP error responses into ApiError and clears stream state", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(
          createResponseStream([
            JSON.stringify({
              detail:
                "Rate limit exceeded.",
            }),
          ]),
          429,
          {
            "content-type":
              "application/json",
          },
        ),
      );

    await expect(
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "test",
        },
      ),
    ).rejects.toThrow(
      "Rate limit exceeded.",
    );

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("handles non-JSON HTTP error bodies", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(
          createResponseStream([
            "Service unavailable.",
          ]),
          503,
          {
            "content-type": "text/plain",
          },
        ),
      );

    await expect(
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "test",
        },
      ),
    ).rejects.toThrow(
      "Service unavailable.",
    );

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);
  });

  it("rejects a successful response with no response body", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(null),
      );

    await expect(
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "test",
        },
      ),
    ).rejects.toThrow(
      "The server returned an empty stream.",
    );

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("emits streamFailed for malformed SSE JSON without crashing the parser", async () => {
    const malformedEvent = [
      "event: chunk",
      'data: {"text": invalid-json}',
      "",
      "",
    ].join("\n");

    const completedEvent =
      createSseEvent(
        "stream_completed",
        {},
      );

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(
          createResponseStream([
            malformedEvent,
            completedEvent,
          ]),
        ),
      );

    const events: ChatStreamEvent[] = [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(
      events.some(
        (event) =>
          event.type ===
          "streamFailed",
      ),
    ).toBe(true);

    expect(
      events.some(
        (event) =>
          event.type ===
          "streamCompleted",
      ),
    ).toBe(true);
  });

  it("does not dispatch late events from an old stream after a new stream starts", async () => {
    const firstStream =
      createDeferredStream();

    const secondStream =
      createDeferredStream();

    global.fetch = vi
      .fn()
      .mockImplementation(
        (
          _url: string,
          init?: RequestInit,
        ) => {
          const signal = init?.signal;

          if (
            signal?.aborted
          ) {
            return Promise.reject(
              new DOMException(
                "Aborted",
                "AbortError",
              ),
            );
          }

          const callCount =
            vi.mocked(global.fetch)
              .mock.calls.length;

          if (callCount === 1) {
            return Promise.resolve(
              createResponse(
                firstStream.stream,
              ),
            );
          }

          return Promise.resolve(
            createResponse(
              secondStream.stream,
            ),
          );
        },
      );

    const firstEvents: ChatStreamEvent[] =
      [];

    const secondEvents: ChatStreamEvent[] =
      [];

    const firstPromise =
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "first",
        },
        {
          onEvent: (event) => {
            firstEvents.push(event);
          },
        },
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(1);

    const secondPromise =
      chatStreamService.stream(
        {
          chat_id: 2,
          prompt: "second",
        },
        {
          onEvent: (event) => {
            secondEvents.push(event);
          },
        },
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(2);

    firstStream.enqueue(
      createSseEvent(
        "chunk",
        {
          text: "STALE",
        },
      ),
    );

    firstStream.enqueue(
      createSseEvent(
        "sources",
        {
          sources: [
            {
              id: 999,
              page_number: 99,
              chunk_index: 99,
              distance: 0.999,
            },
          ],
        },
      ),
    );

    firstStream.enqueue(
      createSseEvent(
        "stream_completed",
        {
          message_id: 999,
        },
      ),
    );

    firstStream.close();

    secondStream.enqueue(
      createSseEvent(
        "chunk",
        {
          text: "CURRENT",
        },
      ),
    );

    secondStream.enqueue(
      createSseEvent(
        "stream_completed",
        {
          message_id: 2,
        },
      ),
    );

    secondStream.close();

    await expect(
      firstPromise,
    ).resolves.toBeUndefined();

    await expect(
      secondPromise,
    ).resolves.toBeUndefined();

    expect(
      firstEvents.filter(
        (event) =>
          event.type ===
            "chunkReceived" ||
          event.type ===
            "sourcesReceived" ||
          event.type ===
            "streamCompleted",
      ),
    ).toEqual([]);

    expect(
      secondEvents,
    ).toEqual([
      {
        type: "chunkReceived",
        chunk: "CURRENT",
      },
      {
        type: "streamCompleted",
        messageId: 2,
      },
    ]);
  });

  it("isolates streams by chat ID when abortChat is called", async () => {
    const firstStream = createDeferredStream();

    let callCount = 0;
    global.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      callCount += 1;
      const currentCall = callCount;
      const signal = init?.signal;

      if (currentCall === 1) {
        return Promise.resolve(createResponse(firstStream.stream));
      }

      return new Promise<Response>((_resolve, reject) => {
        if (signal?.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }

        signal?.addEventListener(
          "abort",
          () => {
            reject(new DOMException("Aborted", "AbortError"));
          },
          { once: true },
        );
      });
    });

    const firstEvents: ChatStreamEvent[] = [];

    const firstPromise = chatStreamService.stream(
      {
        chat_id: 10,
        prompt: "chat ten",
      },
      {
        onEvent: (event) => {
          firstEvents.push(event);
        },
      },
    );

    expect(chatStreamService.currentChatId).toBe(10);

    // abortChat for another chat must not cancel active stream 10
    chatStreamService.abortChat(20);

    expect(chatStreamService.currentChatId).toBe(10);

    firstStream.enqueue(
      createSseEvent("chunk", {
        text: "still active",
      }),
    );
    firstStream.enqueue(createSseEvent("stream_completed", {}));
    firstStream.close();

    await firstPromise;

    expect(firstEvents).toEqual([
      {
        type: "chunkReceived",
        chunk: "still active",
      },
      {
        type: "streamCompleted",
        messageId: undefined,
      },
    ]);

    const secondPromise = chatStreamService.stream({
      chat_id: 20,
      prompt: "chat twenty",
    });

    expect(chatStreamService.currentChatId).toBe(20);

    chatStreamService.abortChat(20);

    await expect(secondPromise).rejects.toThrow(
      "The AI stream was cancelled.",
    );

    expect(chatStreamService.isStreaming).toBe(false);
  });

  it("aborts the active stream and emits cancellation exactly once", async () => {
    global.fetch = vi
      .fn()
      .mockImplementation(
        (
          _url: string,
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
                    "Aborted",
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
                      "Aborted",
                      "AbortError",
                    ),
                  );
                },
                { once: true },
              );
            },
          );
        },
      );

    const cancellationEvents: ChatStreamEvent[] =
      [];

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
              cancellationEvents.push(
                event,
              );
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
      cancellationEvents,
    ).toHaveLength(1);

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("aborts the previous stream when a new stream starts", async () => {
    global.fetch = vi
      .fn()
      .mockImplementation(
        (
          _url: string,
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
                    "Aborted",
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
                      "Aborted",
                      "AbortError",
                    ),
                  );
                },
                { once: true },
              );
            },
          );
        },
      );

    const firstPromise =
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "first",
        },
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(1);

    const secondPromise =
      chatStreamService.stream(
        {
          chat_id: 2,
          prompt: "second",
        },
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(2);

    await expect(
      firstPromise,
    ).rejects.toThrow(
      "The AI stream was cancelled.",
    );

    chatStreamService.abort();

    await expect(
      secondPromise,
    ).rejects.toThrow(
      "The AI stream was cancelled.",
    );

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("does not allow a stale stream to clear the current stream state", async () => {
    const firstStream =
      createDeferredStream();

    const secondStream =
      createDeferredStream();

    global.fetch = vi
      .fn()
      .mockImplementation(
        () => {
          const callCount =
            vi.mocked(global.fetch)
              .mock.calls.length;

          return Promise.resolve(
            createResponse(
              callCount === 1
                ? firstStream.stream
                : secondStream.stream,
            ),
          );
        },
      );

    const firstPromise =
      chatStreamService.stream(
        {
          chat_id: 1,
          prompt: "first",
        },
      );

    const secondPromise =
      chatStreamService.stream(
        {
          chat_id: 2,
          prompt: "second",
        },
      );

    expect(
      chatStreamService.currentChatId,
    ).toBe(2);

    expect(
      chatStreamService.isStreaming,
    ).toBe(true);

    firstStream.enqueue(
      createSseEvent(
        "stream_completed",
        {},
      ),
    );
    firstStream.close();

    await firstPromise;

    expect(
      chatStreamService.currentChatId,
    ).toBe(2);

    expect(
      chatStreamService.isStreaming,
    ).toBe(true);

    secondStream.enqueue(
      createSseEvent(
        "stream_completed",
        {},
      ),
    );
    secondStream.close();

    await secondPromise;

    expect(
      chatStreamService.isStreaming,
    ).toBe(false);

    expect(
      chatStreamService.currentChatId,
    ).toBeNull();
  });

  it("supports multiline SSE data fields", async () => {
    const stream = createResponseStream([
      [
        "event: chunk",
        'data: {"text":"line one\\nline two"}',
        "",
        "",
      ].join("\n"),
      createSseEvent(
        "stream_completed",
        {},
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const chunks: string[] = [];

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
            chunks.push(
              event.chunk,
            );
          }
        },
      },
    );

    expect(chunks).toEqual([
      "line one\nline two",
    ]);
  });

  it("filters invalid retrieved sources instead of leaking malformed source metadata", async () => {
    const stream = createResponseStream([
      createSseEvent(
        "sources",
        {
          sources: [
            {
              id: 1,
              page_number: 2,
              chunk_index: 3,
              distance: 0.1,
            },
            {
              id: "invalid",
              page_number: 2,
              chunk_index: 3,
              distance: 0.2,
            },
            {
              id: 2,
              page_number: null,
              chunk_index: null,
              distance: 0.3,
            },
          ],
        },
      ),
      createSseEvent(
        "stream_completed",
        {},
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    let receivedSources:
      | unknown[]
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
            "sourcesReceived"
          ) {
            receivedSources =
              event.sources;
          }
        },
      },
    );

    expect(
      receivedSources,
    ).toEqual([
      {
        id: 1,
        page_number: 2,
        chunk_index: 3,
        distance: 0.1,
      },
      {
        id: 2,
        page_number: null,
        chunk_index: null,
        distance: 0.3,
      },
    ]);
  });

  it("ignores unknown SSE event types without corrupting the stream", async () => {
    const stream = createResponseStream([
      createSseEvent(
        "unknown_event",
        {
          anything: "ignored",
        },
      ),
      createSseEvent(
        "chunk",
        {
          text: "valid",
        },
      ),
      createSseEvent(
        "stream_completed",
        {},
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const events: ChatStreamEvent[] = [];

    await chatStreamService.stream(
      {
        chat_id: 1,
        prompt: "test",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(events).toEqual([
      {
        type: "chunkReceived",
        chunk: "valid",
      },
      {
        type: "streamCompleted",
        messageId: undefined,
      },
    ]);
  });

  it("sends the expected request payload and authorization header", async () => {
    localStorage.setItem(
      "token",
      "test-token",
    );

    const stream = createResponseStream([
      createSseEvent(
        "stream_completed",
        {},
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    const payload = {
      chat_id: 42,
      prompt: "Hello",
      provider: "gemini" as const,
      model:
        "gemini-2.5-flash" as const,
    };

    await chatStreamService.stream(
      payload,
    );

    expect(
      global.fetch,
    ).toHaveBeenCalledTimes(1);

    const [
      url,
      request,
    ] = vi.mocked(global.fetch)
      .mock.calls[0];

    expect(url).toBe(
      "http://localhost:8000/chat/stream",
    );

    expect(request).toMatchObject({
      method: "POST",
      headers: expect.objectContaining({
        Accept:
          "text/event-stream",
        "Content-Type":
          "application/json",
        Authorization:
          "Bearer test-token",
      }),
      body: JSON.stringify(payload),
    });
  });

  it("does not send an Authorization header when no token exists", async () => {
    localStorage.removeItem(
      "token",
    );

    const stream = createResponseStream([
      createSseEvent(
        "stream_completed",
        {},
      ),
    ]);

    global.fetch = vi
      .fn()
      .mockResolvedValue(
        createResponse(stream),
      );

    await chatStreamService.stream({
      chat_id: 42,
      prompt: "Hello",
    });

    const [
      ,
      request,
    ] = vi.mocked(global.fetch)
      .mock.calls[0];

    const headers =
      request?.headers as Record<
        string,
        string
      >;

    expect(
      headers.Authorization,
    ).toBeUndefined();
  });

  it("can be instantiated independently without sharing stream state", async () => {
    const serviceA =
      new ChatStreamService();

    const serviceB =
      new ChatStreamService();

    const streamA =
      createResponseStream([
        createSseEvent(
          "stream_completed",
          {},
        ),
      ]);

    const streamB =
      createResponseStream([
        createSseEvent(
          "stream_completed",
          {},
        ),
      ]);

    global.fetch = vi
      .fn()
      .mockImplementation(
        () =>
          Promise.resolve(
            createResponse(
              vi
                .mocked(global.fetch)
                .mock.calls.length === 1
                ? streamA
                : streamB,
            ),
          ),
      );

    const promiseA =
      serviceA.stream({
        chat_id: 1,
        prompt: "A",
      });

    const promiseB =
      serviceB.stream({
        chat_id: 2,
        prompt: "B",
      });

    await Promise.all([
      promiseA,
      promiseB,
    ]);

    expect(
      serviceA.isStreaming,
    ).toBe(false);

    expect(
      serviceB.isStreaming,
    ).toBe(false);

    expect(
      serviceA.currentChatId,
    ).toBeNull();

    expect(
      serviceB.currentChatId,
    ).toBeNull();
  });
});