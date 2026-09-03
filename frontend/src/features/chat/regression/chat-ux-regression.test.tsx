import "@testing-library/jest-dom/vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatArea } from "@/features/chat/components/chat-area";
import { ChatComposer } from "@/features/chat/components/chat-composer";
import { CitationSources } from "@/features/chat/components/citation-sources";
import { MessageBubble } from "@/features/chat/components/message-bubble";
import { useChatStore } from "@/features/chat/store/chat-store";
import type {
  AIModel,
  AIProvider,
  ChatMessage,
  RetrievedSource,
} from "@/types/api";

import { chatActions } from "@/features/chat/actions/chat-actions";

vi.mock("@/features/chat/actions/chat-actions", () => ({
  chatActions: {
    sendMessage: vi.fn(),
    stopStreaming: vi.fn(),
    uploadPdf: vi.fn(),
  },
}));

vi.mock("@/features/chat/components/image-attachment-list", () => ({
  ImageAttachmentList: () => null,
}));

vi.mock("@/features/chat/components/pdf-attachment", () => ({
  PdfAttachment: () => null,
}));

vi.mock("@/features/chat/components/model-selector", () => ({
  ModelSelector: ({
    model,
    provider,
  }: {
    model: AIModel;
    provider: AIProvider;
  }) => (
    <div
      data-testid="model-selector"
      data-model={model}
      data-provider={provider}
    />
  ),
}));

vi.mock("@/features/chat/components/message-list", () => ({
  MessageList: ({ chatId }: { chatId: number | null }) => (
    <div data-testid="message-list">Messages for chat {chatId}</div>
  ),
}));

const mockedChatActions = vi.mocked(chatActions);

const CHAT_ID = 101;

const MODEL: AIModel = "gemini-2.5-flash";
const PROVIDER: AIProvider = "gemini";

const SOURCE_A: RetrievedSource = {
  id: 1001,
  page_number: 4,
  chunk_index: 12,
  distance: 0.08,
};

const SOURCE_B: RetrievedSource = {
  id: 1002,
  page_number: 9,
  chunk_index: 21,
  distance: 0.2,
};

function makeAiMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    role: "ai",
    content: "Assistant response.",
    ...overrides,
  };
}

function activateChat(chatId = CHAT_ID): void {
  useChatStore.getState().setActiveChat(chatId);
}

function setStreaming(chatId = CHAT_ID): void {
  useChatStore.getState().setStreamingStatus(chatId, "streaming");
}

function setStreamError(chatId = CHAT_ID): void {
  useChatStore.getState().setStreamingStatus(chatId, "error");
}

beforeEach(() => {
  vi.clearAllMocks();

  useChatStore.getState().reset();

  mockedChatActions.sendMessage.mockResolvedValue(undefined);
  mockedChatActions.stopStreaming.mockImplementation(() => undefined);
  mockedChatActions.uploadPdf.mockResolvedValue({
    filename: "document.pdf",
    chunksCount: 10,
  });
});

describe("Phase 3.3 — Final Chat UX regression / polish", () => {
  describe("1. Empty / whitespace submission prevention", () => {
    it("keeps Send disabled for an empty prompt", () => {
      activateChat();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const sendButton = screen.getByRole("button", {
        name: "Send message",
      });

      expect(sendButton).toBeDisabled();
      expect(mockedChatActions.sendMessage).not.toHaveBeenCalled();
    });

    it("keeps Send disabled for whitespace-only input", () => {
      activateChat();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const textarea = screen.getByRole("textbox", {
        name: "Chat prompt",
      });

      fireEvent.change(textarea, {
        target: {
          value: "   \n\t  ",
        },
      });

      expect(
        screen.getByRole("button", {
          name: "Send message",
        }),
      ).toBeDisabled();

      fireEvent.keyDown(textarea, {
        key: "Enter",
        code: "Enter",
        charCode: 13,
      });

      expect(mockedChatActions.sendMessage).not.toHaveBeenCalled();
    });

    it("trims a valid prompt before sending", async () => {
      activateChat();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const textarea = screen.getByRole("textbox", {
        name: "Chat prompt",
      });

      fireEvent.change(textarea, {
        target: {
          value: "   Explain this document   ",
        },
      });

      fireEvent.click(
        screen.getByRole("button", {
          name: "Send message",
        }),
      );

      await waitFor(() => {
        expect(mockedChatActions.sendMessage).toHaveBeenCalledTimes(1);
      });

      expect(mockedChatActions.sendMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          chatId: CHAT_ID,
          prompt: "Explain this document",
          model: MODEL,
          provider: PROVIDER,
        }),
      );
    });

    it("submits with Enter but preserves multiline input with Shift+Enter", async () => {
      activateChat();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const textarea = screen.getByRole("textbox", {
        name: "Chat prompt",
      });

      fireEvent.change(textarea, {
        target: {
          value: "Line one",
        },
      });

      fireEvent.keyDown(textarea, {
        key: "Enter",
        code: "Enter",
        charCode: 13,
        shiftKey: true,
      });

      expect(mockedChatActions.sendMessage).not.toHaveBeenCalled();

      fireEvent.change(textarea, {
        target: {
          value: "Line one\nLine two",
        },
      });

      expect(textarea).toHaveValue("Line one\nLine two");

      fireEvent.keyDown(textarea, {
        key: "Enter",
        code: "Enter",
        charCode: 13,
      });

      await waitFor(() => {
        expect(mockedChatActions.sendMessage).toHaveBeenCalledTimes(1);
      });

      expect(mockedChatActions.sendMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: "Line one\nLine two",
        }),
      );
    });

    it("does not allow submission when no active chat exists", () => {
      render(<ChatComposer chatId={null} model={MODEL} provider={PROVIDER} />);

      const textarea = screen.getByRole("textbox", {
        name: "Chat prompt",
      });

      const sendButton = screen.getByRole("button", {
        name: "Send message",
      });

      expect(textarea).toBeDisabled();
      expect(sendButton).toBeDisabled();

      expect(mockedChatActions.sendMessage).not.toHaveBeenCalled();
    });
  });

  describe("2. MessageBubble streaming presentation vs completed state", () => {
    it("shows the streaming cursor while an AI message is streaming", () => {
      const { container } = render(
        <MessageBubble
          message={makeAiMessage({
            content: "Partial response",
          })}
          isStreaming
        />,
      );

      expect(screen.getByText("Partial response")).toBeDefined();

      const streamingCursor = container.querySelector("span.animate-pulse");

      expect(streamingCursor).not.toBeNull();
      expect(streamingCursor).toHaveAttribute("aria-hidden", "true");
    });

    it("removes the streaming cursor after completion", () => {
      const { container } = render(
        <MessageBubble
          message={makeAiMessage({
            content: "Completed response",
          })}
          isStreaming={false}
        />,
      );

      expect(screen.getByText("Completed response")).toBeDefined();

      const streamingCursor = container.querySelector("span.animate-pulse");

      expect(streamingCursor).toBeNull();
    });

    it("renders user messages without the AI streaming presentation", () => {
      const { container } = render(
        <MessageBubble
          message={{
            role: "user",
            content: "User message",
          }}
          isStreaming
        />,
      );

      expect(screen.getByText("User message")).toBeDefined();

      const streamingCursor = container.querySelector("span.animate-pulse");

      expect(streamingCursor).toBeNull();
    });
  });

  describe("3. Citation gating during streaming and after completion", () => {
    it("does not expose citations while an AI response is streaming", () => {
      render(
        <MessageBubble
          message={makeAiMessage({
            content: "Streaming answer",
            sources: [SOURCE_A],
          })}
          isStreaming
        />,
      );

      expect(screen.getByText("Streaming answer")).toBeDefined();

      expect(
        screen.queryByRole("button", {
          name: /1 source/i,
        }),
      ).toBeNull();

      expect(screen.queryByText("Page 4")).toBeNull();
      expect(screen.queryByText("Chunk 12")).toBeNull();
    });

    it("reveals citations once the AI response is completed", () => {
      render(
        <MessageBubble
          message={makeAiMessage({
            content: "Completed answer",
            sources: [SOURCE_A],
          })}
          isStreaming={false}
        />,
      );

      const citationButton = screen.getByRole("button", {
        name: /1 source/i,
      });

      expect(citationButton).toBeDefined();
      expect(citationButton).toHaveAttribute("aria-expanded", "false");

      fireEvent.click(citationButton);

      expect(citationButton).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("Page 4")).toBeDefined();
      expect(screen.getByText("Chunk 12")).toBeDefined();
      expect(screen.getByText("Relevance 92%")).toBeDefined();
    });

    it("does not render a citation control when sources are absent", () => {
      render(
        <MessageBubble
          message={makeAiMessage({
            content: "No-source answer",
          })}
          isStreaming={false}
        />,
      );

      expect(
        screen.queryByRole("button", {
          name: /source/i,
        }),
      ).toBeNull();
    });

    it("does not render a citation control for an empty source array", () => {
      render(
        <MessageBubble
          message={makeAiMessage({
            content: "No retrieved sources",
            sources: [],
          })}
          isStreaming={false}
        />,
      );

      expect(
        screen.queryByRole("button", {
          name: /source/i,
        }),
      ).toBeNull();
    });

    it("supports expanding and collapsing multiple citations", () => {
      render(<CitationSources sources={[SOURCE_A, SOURCE_B]} />);

      const button = screen.getByRole("button", {
        name: /2 sources/i,
      });

      expect(button).toHaveAttribute("aria-expanded", "false");

      fireEvent.click(button);

      expect(button).toHaveAttribute("aria-expanded", "true");

      expect(screen.getByText("Source 1")).toBeDefined();
      expect(screen.getByText("Source 2")).toBeDefined();
      expect(screen.getByText("Page 4")).toBeDefined();
      expect(screen.getByText("Page 9")).toBeDefined();

      fireEvent.click(button);

      expect(button).toHaveAttribute("aria-expanded", "false");
    });
  });

  describe("4. Long multiline content and word wrapping", () => {
    it("preserves multiline content and enables wrapping for long content", () => {
      const longToken =
        "https://example.com/this-is-an-extremely-long-unbroken-token-that-must-not-force-the-chat-layout-to-overflow-horizontally";

      const multilineContent = `First line\nSecond line\n\n${longToken}\nFinal line`;

      const { container } = render(
        <MessageBubble
          message={makeAiMessage({
            content: multilineContent,
          })}
        />,
      );

      const content = screen.getByText(
        (text) =>
          text.includes("First line") &&
          text.includes("Second line") &&
          text.includes("Final line"),
      );

      expect(content).toBeInTheDocument();
      expect(content.textContent).toContain("First line");
      expect(content.textContent).toContain("Second line");
      expect(content.textContent).toContain(longToken);
      expect(content.textContent).toContain("Final line");

      const bubble = container.querySelector(
        ".whitespace-pre-wrap, .break-words, .break-word",
      );

      expect(bubble).not.toBeNull();
    });

    it("preserves multiline system messages as well", () => {
      render(
        <MessageBubble
          message={{
            role: "system",
            content: "System line one\nSystem line two",
          }}
        />,
      );

      const content = screen.getByText(
        (text) =>
          text.includes("System line one") && text.includes("System line two"),
      );

      expect(content).toBeInTheDocument();
    });
  });

  describe("5. Cancel and retry interaction states", () => {
    it("shows Stop generating instead of Send while streaming", () => {
      activateChat();
      setStreaming();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      expect(
        screen.getByRole("button", {
          name: "Stop generating",
        }),
      ).toBeDefined();

      expect(
        screen.queryByRole("button", {
          name: "Send message",
        }),
      ).toBeNull();
    });

    it("invokes stopStreaming when Stop generating is pressed", () => {
      activateChat();
      setStreaming();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      fireEvent.click(
        screen.getByRole("button", {
          name: "Stop generating",
        }),
      );

      expect(mockedChatActions.stopStreaming).toHaveBeenCalledTimes(1);
    });

    it("does not permit message submission while streaming", () => {
      activateChat();
      setStreaming();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const textarea = screen.getByRole("textbox", {
        name: "Chat prompt",
      });

      expect(textarea).toBeDisabled();

      fireEvent.keyDown(textarea, {
        key: "Enter",
        code: "Enter",
        charCode: 13,
      });

      expect(mockedChatActions.sendMessage).not.toHaveBeenCalled();
    });

    it("shows the retry action only when the active chat has a stream error", () => {
      activateChat();
      setStreamError();

      render(<ChatArea />);

      expect(
        screen.getByText("Response incomplete due to an error."),
      ).toBeDefined();

      expect(
        screen.getByRole("button", {
          name: "Retry",
        }),
      ).toBeDefined();
    });

    it("does not show Retry during normal idle state", () => {
      activateChat();

      render(<ChatArea />);

      expect(
        screen.queryByRole("button", {
          name: "Retry",
        }),
      ).toBeNull();
    });

    it("disables Retry while a retry request is pending", async () => {
      activateChat();
      setStreamError();

      let resolveRetry!: () => void;

      mockedChatActions.sendMessage.mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            resolveRetry = resolve;
          }),
      );

      useChatStore.getState().setMessages(CHAT_ID, [
        {
          role: "user",
          content: "Retry this question",
        },
      ]);

      render(<ChatArea />);

      const retryButton = screen.getByRole("button", {
        name: "Retry",
      });

      fireEvent.click(retryButton);

      await waitFor(() => {
        const retryingBtn = screen.getByRole("button", {
          name: /retrying/i,
        });
        expect(retryingBtn).toBeDisabled();
      });

      expect(mockedChatActions.sendMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          chatId: CHAT_ID,
          prompt: "Retry this question",
        }),
      );

      resolveRetry();

      await waitFor(() => {
        expect(
          screen.queryByRole("button", {
            name: /retrying/i,
          }),
        ).toBeNull();
      });
    });
  });

  describe("6. History empty state and loading skeleton", () => {
    it("shows the conversation empty state when the active chat has no messages", () => {
      activateChat();

      useChatStore.getState().setMessages(CHAT_ID, []);

      render(<ChatArea />);

      expect(
        screen.getByRole("heading", {
          name: "Start a conversation",
        }),
      ).toBeDefined();

      expect(
        screen.getByText(
          "Type a message below or attach files to begin chatting with the AI.",
        ),
      ).toBeDefined();

      expect(screen.queryByTestId("message-list")).toBeNull();
    });

    it("shows the message skeleton while the active chat is loading", () => {
      activateChat();

      useChatStore.getState().setMessages(CHAT_ID, [
        {
          role: "user",
          content: "Existing message",
        },
      ]);

      useChatStore.getState().setChatLoading(CHAT_ID, true);

      const { container } = render(<ChatArea />);

      expect(screen.queryByText("Existing message")).toBeNull();
      expect(screen.queryByTestId("message-list")).toBeNull();

      const skeletons = container.querySelectorAll(".animate-pulse");

      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("prefers loading skeleton over the empty state", () => {
      activateChat();

      useChatStore.getState().setMessages(CHAT_ID, []);
      useChatStore.getState().setChatLoading(CHAT_ID, true);

      render(<ChatArea />);

      expect(
        screen.queryByRole("heading", {
          name: "Start a conversation",
        }),
      ).toBeNull();
    });

    it("renders the message list once loading finishes and messages exist", () => {
      activateChat();

      useChatStore.getState().setMessages(CHAT_ID, [
        {
          role: "user",
          content: "Loaded message",
        },
      ]);

      render(<ChatArea />);

      expect(screen.getByTestId("message-list")).toHaveTextContent(
        `Messages for chat ${CHAT_ID}`,
      );
    });
  });

  describe("7. Accessible button semantics", () => {
    it("exposes the composer controls through accessible names", () => {
      activateChat();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      expect(
        screen.getByRole("textbox", {
          name: "Chat prompt",
        }),
      ).toBeDefined();

      expect(
        screen.getByRole("button", {
          name: "Attach image",
        }),
      ).toBeDefined();

      expect(
        screen.getByRole("button", {
          name: "Attach PDF",
        }),
      ).toBeDefined();

      expect(
        screen.getByRole("button", {
          name: "Send message",
        }),
      ).toBeDisabled();
    });

    it("uses a real button with correct toggle semantics for citations", () => {
      render(<CitationSources sources={[SOURCE_A]} />);

      const citationButton = screen.getByRole("button", {
        name: /1 source/i,
      });

      expect(citationButton).toHaveAttribute("aria-expanded", "false");

      const controlledId = citationButton.getAttribute("aria-controls");

      expect(controlledId).toBeTruthy();

      const controlledRegion = document.getElementById(controlledId as string);

      expect(controlledRegion).not.toBeNull();
      expect(controlledRegion).toHaveAttribute("hidden");

      fireEvent.click(citationButton);

      expect(citationButton).toHaveAttribute("aria-expanded", "true");

      expect(controlledRegion).not.toHaveAttribute("hidden");
    });

    it("uses Stop generating as an accessible button during streaming", () => {
      activateChat();
      setStreaming();

      render(
        <ChatComposer chatId={CHAT_ID} model={MODEL} provider={PROVIDER} />,
      );

      const stopButton = screen.getByRole("button", {
        name: "Stop generating",
      });

      expect(stopButton).toHaveAttribute("type", "button");
      expect(stopButton).not.toBeDisabled();
    });

    it("keeps Retry as an accessible button in the error state", () => {
      activateChat();
      setStreamError();

      useChatStore.getState().setMessages(CHAT_ID, [
        {
          role: "user",
          content: "Failed request",
        },
      ]);

      render(<ChatArea />);

      const retryButton = screen.getByRole("button", {
        name: "Retry",
      });

      expect(retryButton).toHaveAttribute("type", "button");
      expect(retryButton).not.toBeDisabled();

      const errorStatus = screen.getByRole("status");

      expect(errorStatus).toHaveAttribute("aria-live", "polite");

      expect(
        within(errorStatus).getByText("Response incomplete due to an error."),
      ).toBeDefined();
    });
  });
});
