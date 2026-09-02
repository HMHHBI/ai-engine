import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ChatStreamService,
  type ChatStreamEvent,
} from "./chat-stream-service";

import type { StreamPayload } from "@/types/api";

const payload: StreamPayload = {
  chat_id: 1,
  prompt: "Hello",
  task: "general",
  model: "gemini-2.5-flash",
};

function createResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatStreamService", () => {
  it("emits started, chunks, and completed events", async () => {
    const service = new ChatStreamService();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(createResponse(["Hello ", "world"])),
    );

    const events: ChatStreamEvent[] = [];

    await service.stream(payload, {
      onEvent: (event) => {
        events.push(event);
      },
    });

    expect(events).toEqual([
      { type: "streamStarted" },
      { type: "chunkReceived", chunk: "Hello " },
      { type: "chunkReceived", chunk: "world" },
      { type: "streamCompleted" },
    ]);

    expect(service.isStreaming).toBe(false);
  });

  it("maps 429 to RATE_LIMITED", async () => {
    const service = new ChatStreamService();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Too many requests",
          }),
          {
            status: 429,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const events: ChatStreamEvent[] = [];

    await expect(
      service.stream(payload, {
        onEvent: (event) => {
          events.push(event);
        },
      }),
    ).rejects.toMatchObject({
      code: "RATE_LIMITED",
      status: 429,
    });

    expect(events).toContainEqual({
      type: "streamStarted",
    });

    expect(events).toContainEqual(
      expect.objectContaining({
        type: "streamFailed",
        error: expect.objectContaining({
          code: "RATE_LIMITED",
          status: 429,
        }),
      }),
    );
  });

  it("maps 502 to PROVIDER_DOWN", async () => {
    const service = new ChatStreamService();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Provider unavailable",
          }),
          {
            status: 502,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    await expect(service.stream(payload)).rejects.toMatchObject({
      code: "PROVIDER_DOWN",
      status: 502,
    });
  });

  it("aborts an active stream", async () => {
    const service = new ChatStreamService();
    let receivedSignal: AbortSignal | null | undefined;

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        receivedSignal = init?.signal;
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const events: ChatStreamEvent[] = [];

    const promise = service.stream(payload, {
      onEvent: (event) => {
        events.push(event);
      },
    });

    // Verify isStreaming synchronously right after start
    expect(service.isStreaming).toBe(true);

    service.abort();

    await expect(promise).rejects.toMatchObject({
      code: "STREAM_ABORTED",
    });

    expect(receivedSignal?.aborted).toBe(true);
    expect(events).toContainEqual({
      type: "streamCancelled",
    });
    expect(service.isStreaming).toBe(false);
  });

  it("rejects when the server returns an empty stream", async () => {
    const service = new ChatStreamService();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(null, {
          status: 200,
        }),
      ),
    );

    await expect(service.stream(payload)).rejects.toMatchObject({
      code: "STREAM_ERROR",
    });
  });
});