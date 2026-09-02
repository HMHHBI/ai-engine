import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatStreamService } from "./chat-stream-service";

describe("chatStreamService", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
    chatStreamService.abort();
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("completes streaming flow and fires handlers", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("Hello "));
        controller.enqueue(encoder.encode("world!"));
        controller.close();
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ "content-type": "text/event-stream" }),
    });

    const chunks: string[] = [];
    let completed = false;

    await chatStreamService.stream(
      { chat_id: 1, prompt: "test" },
      {
        onEvent: (event) => {
          if (event.type === "chunkReceived") chunks.push(event.chunk);
          if (event.type === "streamCompleted") completed = true;
        },
      },
    );

    expect(chunks).toEqual(["Hello ", "world!"]);
    expect(completed).toBe(true);
    expect(chatStreamService.isStreaming).toBe(false);
  });

  it("handles abort gracefully and marks stream cancelled", async () => {
    global.fetch = vi.fn().mockImplementation((_url, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        const signal = init?.signal;
        if (signal?.aborted) {
          reject(new DOMException("The user aborted a request.", "AbortError"));
          return;
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The user aborted a request.", "AbortError"));
        });
      });
    });

    let cancelled = false;

    const streamPromise = chatStreamService.stream(
      { chat_id: 1, prompt: "test" },
      {
        onEvent: (event) => {
          if (event.type === "streamCancelled") cancelled = true;
        },
      },
    );

    chatStreamService.abort();

    await expect(streamPromise).rejects.toThrow("The AI stream was cancelled.");
    expect(cancelled).toBe(true);
  });

  it("aborts active stream when a new stream starts", async () => {
    global.fetch = vi.fn().mockImplementation((_url, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        const signal = init?.signal;
        if (signal?.aborted) {
          reject(new DOMException("The user aborted a request.", "AbortError"));
          return;
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The user aborted a request.", "AbortError"));
        });
      });
    });

    const stream1 = chatStreamService.stream(
      { chat_id: 1, prompt: "first" },
      {},
    );

    expect(chatStreamService.currentChatId).toBe(1);

    const stream2 = chatStreamService.stream(
      { chat_id: 2, prompt: "second" },
      {},
    );

    expect(chatStreamService.currentChatId).toBe(2);

    await expect(stream1).rejects.toThrow("The AI stream was cancelled.");
    chatStreamService.abort();
    await expect(stream2).rejects.toThrow("The AI stream was cancelled.");
  });
});