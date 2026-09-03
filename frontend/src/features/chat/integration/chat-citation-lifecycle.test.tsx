import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatActions } from "@/features/chat/actions/chat-actions";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { MessageBubble } from "@/features/chat/components/message-bubble";
import { chatStreamService } from "@/features/chat/stream/chat-stream-service";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import type { ChatMessage, ChatSession, RetrievedSource } from "@/types/api";

import { chatApi } from "@/lib/api/chat";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    uploadPdf: vi.fn(),
    get: vi.fn(),
    getAll: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    updateTitle: vi.fn(),
  },
}));

const mockedChatApi = vi.mocked(chatApi);

const CHAT_A = 101;
const CHAT_B = 202;

const SOURCE_A1: RetrievedSource = {
  id: 1001,
  page_number: 4,
  chunk_index: 12,
  distance: 0.08,
};

const SOURCE_A2: RetrievedSource = {
  id: 1002,
  page_number: 7,
  chunk_index: 18,
  distance: 0.2,
};

const SOURCE_B1: RetrievedSource = {
  id: 2001,
  page_number: 2,
  chunk_index: 5,
  distance: 0.05,
};

const SOURCE_RETRY_1: RetrievedSource = {
  id: 3001,
  page_number: 10,
  chunk_index: 21,
  distance: 0.1,
};

const SOURCE_RETRY_2: RetrievedSource = {
  id: 3002,
  page_number: 14,
  chunk_index: 31,
  distance: 0.25,
};

function makeSession(
  chatId: number,
  overrides: Partial<ChatSession> = {},
): ChatSession {
  const timestamp = "2026-09-03T10:00:00.000Z";

  return {
    id: chatId,
    user_id: 1,
    title: `Chat ${chatId}`,
    created_at: timestamp,
    updated_at: timestamp,
    has_pdf: false,
    ...overrides,
  };
}

function seedChat(
  chatId: number,
  options: {
    messages?: ChatMessage[];
    hasPdf?: boolean;
  } = {},
): void {
  const { messages = [], hasPdf = false } = options;

  useChatStore.getState().setMessages(chatId, messages);
  useChatStore.getState().setActiveChat(chatId);

  useChatSessionStore.getState().addSession(
    makeSession(chatId, {
      has_pdf: hasPdf,
    }),
  );
}

function getMessages(chatId: number): ChatMessage[] {
  return useChatStore.getState().messagesByChat[chatId] ?? [];
}

function getLastMessage(chatId: number): ChatMessage | undefined {
  const messages = getMessages(chatId);
  return messages[messages.length - 1];
}

function makeSseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function makeSseResponse(
  events: string[],
  options: {
    delayAfter?: number;
  } = {},
): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(event));

        await Promise.resolve();
      }

      if (options.delayAfter) {
        await new Promise((resolve) => setTimeout(resolve, options.delayAfter));
      }

      controller.close();
    },
  });

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
    },
  });
}

function mockSuccessfulStream(
  sources: RetrievedSource[] = [],
  chunks: string[] = ["Answer"],
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      makeSseResponse([
        makeSseEvent("stream_started", {
          provider: "gemini",
          model: "gemini-2.5-flash",
        }),

        ...(sources.length > 0
          ? [
              makeSseEvent("sources", {
                sources,
              }),
            ]
          : []),

        ...chunks.map((text) =>
          makeSseEvent("chunk", {
            text,
          }),
        ),

        makeSseEvent("stream_completed", {
          message_id: 9001,
        }),
      ]),
    ),
  );
}

function mockSourcesThenFailure(sources: RetrievedSource[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      makeSseResponse([
        makeSseEvent("stream_started", {
          provider: "gemini",
          model: "gemini-2.5-flash",
        }),

        makeSseEvent("sources", {
          sources,
        }),

        makeSseEvent("chunk", {
          text: "Partial answer",
        }),

        makeSseEvent("stream_error", {
          code: "MODEL_ERROR",
          message: "Model failed after retrieval.",
        }),
      ]),
    ),
  );
}

function createPendingStreamResponse(initialEvents: string[]): {
  response: Response;
  release: () => void;
} {
  const encoder = new TextEncoder();

  let releaseStream: (() => void) | undefined;

  const releasePromise = new Promise<void>((resolve) => {
    releaseStream = resolve;
  });

  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const event of initialEvents) {
        controller.enqueue(encoder.encode(event));
      }

      await releasePromise;

      controller.enqueue(
        encoder.encode(
          makeSseEvent("sources", {
            sources: [SOURCE_B1],
          }),
        ),
      );

      controller.enqueue(
        encoder.encode(
          makeSseEvent("chunk", {
            text: "late answer",
          }),
        ),
      );

      controller.enqueue(
        encoder.encode(
          makeSseEvent("stream_completed", {
            message_id: 9999,
          }),
        ),
      );

      controller.close();
    },
    cancel() {
      releaseStream?.();
    },
  });

  return {
    response: new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
      },
    }),
    release: () => {
      releaseStream?.();
    },
  };
}

function renderLastAiMessage(chatId: number): void {
  const message = getLastMessage(chatId);

  if (!message) {
    throw new Error(`No message exists for chat ${chatId}.`);
  }

  render(<MessageBubble message={message} isStreaming={false} />);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();

  useChatStore.getState().reset();
  useChatSessionStore.getState().reset();

  mockedChatApi.uploadPdf.mockReset();
  mockedChatApi.get.mockReset();
  mockedChatApi.getAll.mockReset();
  mockedChatApi.create.mockReset();
  mockedChatApi.delete.mockReset();
  mockedChatApi.updateTitle.mockReset();

  chatStreamService.abort();

  localStorage.clear();
});

describe("Phase 3.2 — End-to-End Citation Lifecycle", () => {
  it("runs PDF → question → sources → answer → rendered citations", async () => {
    seedChat(CHAT_A);

    mockedChatApi.uploadPdf.mockResolvedValue({
      filename: "knowledge.pdf",
      chunks_count: 12,
    });

    await chatActions.uploadPdf(
      CHAT_A,
      new File(["knowledge"], "knowledge.pdf", {
        type: "application/pdf",
      }),
    );

    expect(useChatStore.getState().pdfStateByChat[CHAT_A]?.status).toBe(
      "ready",
    );

    expect(
      useChatSessionStore
        .getState()
        .sessions.find((session) => session.id === CHAT_A)?.has_pdf,
    ).toBe(true);

    mockSuccessfulStream([SOURCE_A1], ["The answer ", "comes ", "from PDF."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "What does the PDF say?",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const messages = getMessages(CHAT_A);
    const assistant = messages[messages.length - 1];

    expect(assistant.role).toBe("ai");
    expect(assistant.content).toBe("The answer comes from PDF.");
    expect(assistant.sources).toEqual([SOURCE_A1]);

    renderLastAiMessage(CHAT_A);

    expect(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    ).toBeDefined();

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Page 4")).toBeDefined();

    expect(screen.getByText("Chunk 12")).toBeDefined();

    expect(screen.getByText("Relevance 92%")).toBeDefined();
  });

  it("does not render citations when no PDF exists", async () => {
    seedChat(CHAT_A, {
      hasPdf: false,
    });

    mockSuccessfulStream([], ["Normal answer."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Answer without a PDF.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const assistant = getLastMessage(CHAT_A);

    expect(assistant?.content).toBe("Normal answer.");
    expect(assistant?.sources).toBeUndefined();

    renderLastAiMessage(CHAT_A);

    expect(
      screen.queryByRole("button", {
        name: /source/i,
      }),
    ).toBeNull();
  });

  it("does not render citations when retrieval returns zero chunks", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    mockSuccessfulStream([], ["No matching information was found."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Find something unavailable.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const assistant = getLastMessage(CHAT_A);

    expect(assistant?.content).toBe("No matching information was found.");

    expect(assistant?.sources ?? []).toEqual([]);

    renderLastAiMessage(CHAT_A);

    expect(
      screen.queryByRole("button", {
        name: /source/i,
      }),
    ).toBeNull();
  });

  it("preserves multiple-source ordering and renders each relevance score", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    mockSuccessfulStream([SOURCE_A1, SOURCE_A2], ["Combined answer."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Compare both sources.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const assistant = getLastMessage(CHAT_A);

    expect(assistant?.sources).toEqual([SOURCE_A1, SOURCE_A2]);

    renderLastAiMessage(CHAT_A);

    fireEvent.click(
      screen.getByRole("button", {
        name: /2 sources/i,
      }),
    );

    expect(screen.getByText("Source 1")).toBeDefined();

    expect(screen.getByText("Source 2")).toBeDefined();

    expect(screen.getByText("Page 4")).toBeDefined();

    expect(screen.getByText("Page 7")).toBeDefined();

    expect(screen.getByText("Relevance 92%")).toBeDefined();

    expect(screen.getByText("Relevance 80%")).toBeDefined();

    const sourceLabels = screen.getAllByText(/^Source [12]$/);

    expect(sourceLabels).toHaveLength(2);
    expect(sourceLabels[0].textContent).toBe("Source 1");
    expect(sourceLabels[1].textContent).toBe("Source 2");
  });

  it("attaches sources before chunks without losing citations", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    mockSuccessfulStream([SOURCE_A1], ["First ", "second ", "third."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Explain the document.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const messages = getMessages(CHAT_A);
    const assistant = messages[messages.length - 1];

    expect(assistant.content).toBe("First second third.");

    expect(assistant.sources).toEqual([SOURCE_A1]);

    renderLastAiMessage(CHAT_A);

    expect(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    ).toBeDefined();
  });

  it("isolates sources when the stream fails after sources arrive", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    mockSourcesThenFailure([SOURCE_A1]);

    await expect(
      chatActions.sendMessage({
        chatId: CHAT_A,
        prompt: "Trigger a provider failure.",
        model: "gemini-2.5-flash",
        provider: "gemini",
      }),
    ).rejects.toThrow("Model failed after retrieval.");

    const assistant = getLastMessage(CHAT_A);

    expect(assistant?.content).toBe("Partial answer");

    expect(assistant?.sources).toEqual([SOURCE_A1]);

    expect(useChatStore.getState().streamingStatusByChat[CHAT_A]).toBe("error");

    renderLastAiMessage(CHAT_A);

    expect(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    ).toBeDefined();
  });

  it("isolates citations when cancellation occurs after sources", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    const { response, release } = createPendingStreamResponse([
      makeSseEvent("stream_started", {
        provider: "gemini",
        model: "gemini-2.5-flash",
      }),

      makeSseEvent("sources", {
        sources: [SOURCE_A1],
      }),

      makeSseEvent("chunk", {
        text: "partial",
      }),
    ]);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const sendPromise = chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Cancel this request.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    await waitFor(() => {
      expect(getLastMessage(CHAT_A)?.sources).toEqual([SOURCE_A1]);
    });

    expect(getLastMessage(CHAT_A)?.content).toBe("partial");

    chatActions.stopStreaming();
    useChatStore.getState().setStreamingStatus(CHAT_A, "cancelled");

    release();

    await sendPromise.catch(() => {});

    const assistant = getLastMessage(CHAT_A);

    expect(assistant?.sources).toEqual([SOURCE_A1]);
    expect(assistant?.content).toBe("partial");
    expect(useChatStore.getState().streamingStatusByChat[CHAT_A]).toBe(
      "cancelled",
    );

    renderLastAiMessage(CHAT_A);

    expect(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    ).toBeDefined();
  });

  it("prevents sources from chat A from appearing in chat B", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    seedChat(CHAT_B, {
      hasPdf: true,
    });

    mockSuccessfulStream([SOURCE_A1], ["Answer from A."]);

    const requestA = chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Question for A.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    await requestA;

    expect(getLastMessage(CHAT_A)?.sources).toEqual([SOURCE_A1]);

    mockSuccessfulStream([SOURCE_B1], ["Answer from B."]);

    await chatActions.sendMessage({
      chatId: CHAT_B,
      prompt: "Question for B.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    expect(getLastMessage(CHAT_A)?.sources).toEqual([SOURCE_A1]);

    expect(getLastMessage(CHAT_B)?.sources).toEqual([SOURCE_B1]);

    expect(getLastMessage(CHAT_B)?.sources).not.toContain(SOURCE_A1);

    renderLastAiMessage(CHAT_B);

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Page 2")).toBeDefined();

    expect(screen.queryByText("Page 4")).toBeNull();
  });

  it("replaces old citations on retry instead of inheriting them", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
    });

    mockSuccessfulStream([SOURCE_RETRY_1], ["First attempt."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Try this question.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    expect(getLastMessage(CHAT_A)?.sources).toEqual([SOURCE_RETRY_1]);

    mockSuccessfulStream([SOURCE_RETRY_2], ["Retry succeeded."]);

    await chatActions.sendMessage({
      chatId: CHAT_A,
      prompt: "Try this question again.",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    const messages = getMessages(CHAT_A);
    const assistantMessages = messages.filter(
      (message) => message.role === "ai",
    );

    expect(assistantMessages).toHaveLength(2);

    expect(assistantMessages[0].sources).toEqual([SOURCE_RETRY_1]);

    expect(assistantMessages[1].sources).toEqual([SOURCE_RETRY_2]);

    expect(assistantMessages[1].sources).not.toContain(SOURCE_RETRY_1);

    render(
      <MessageBubble message={assistantMessages[1]} isStreaming={false} />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /1 source/i,
      }),
    );

    expect(screen.getByText("Page 14")).toBeDefined();

    expect(screen.queryByText("Page 10")).toBeNull();
  });

  it("does not persist sources across hydration when the backend message has no source metadata", async () => {
    seedChat(CHAT_A, {
      hasPdf: true,
      messages: [
        {
          id: 1,
          chat_id: CHAT_A,
          role: "user",
          content: "What is in the PDF?",
        },
        {
          id: 2,
          chat_id: CHAT_A,
          role: "ai",
          content: "Persisted answer.",
          sources: [SOURCE_A1],
        },
      ],
    });

    mockedChatApi.get.mockResolvedValue([
      {
        id: 1,
        chat_id: CHAT_A,
        role: "user",
        content: "What is in the PDF?",
      },
      {
        id: 2,
        chat_id: CHAT_A,
        role: "ai",
        content: "Persisted answer.",
      },
    ]);

    const loaded = await chatSessionActions.loadChat(CHAT_A);

    expect(loaded).toBe(true);

    const hydratedAssistant = getLastMessage(CHAT_A);

    expect(hydratedAssistant?.content).toBe("Persisted answer.");

    expect(hydratedAssistant?.sources).toBeUndefined();

    renderLastAiMessage(CHAT_A);

    expect(
      screen.queryByRole("button", {
        name: /source/i,
      }),
    ).toBeNull();
  });
});
