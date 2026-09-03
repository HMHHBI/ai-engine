import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatSessionActions } from "./chat-session-actions";
import { chatApi } from "@/lib/api/chat";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import type { ChatMessage, ChatSession } from "@/types/api";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    getAll: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    updateTitle: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("chatSessionActions", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
    useChatSessionStore.getState().reset();
    chatSessionActions.invalidateHydration();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads chats and sets them in descending order of updated_at", async () => {
    const mockSessions: ChatSession[] = [
      {
        id: 1,
        user_id: 1,
        title: "Older Chat",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T10:00:00Z",
        has_pdf: false,
      },
      {
        id: 2,
        user_id: 1,
        title: "Newer Chat",
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T10:00:00Z",
        has_pdf: false,
      },
    ];

    vi.mocked(chatApi.getAll).mockResolvedValue(mockSessions);

    await chatSessionActions.loadChats();

    const sessions = useChatSessionStore.getState().sessions;
    expect(sessions[0].id).toBe(2);
    expect(sessions[1].id).toBe(1);
    expect(useChatSessionStore.getState().isLoading).toBe(false);
  });

  it("loads a chat, stores messages, and sets activeChatId", async () => {
    const mockMessages: ChatMessage[] = [
      { id: 101, role: "user", content: "Hello" },
      { id: 102, role: "ai", content: "Hi there!" },
    ];

    vi.mocked(chatApi.get).mockResolvedValue(mockMessages);

    const loaded = await chatSessionActions.loadChat(42);

    expect(loaded).toBe(true);
    expect(chatApi.get).toHaveBeenCalledWith(42);
    expect(useChatStore.getState().activeChatId).toBe(42);
    expect(useChatStore.getState().messagesByChat[42]).toEqual(mockMessages);
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("prevents stale hydration responses from overwriting the latest chat navigation", async () => {
    let resolveChat42!: (msgs: ChatMessage[]) => void;
    const chat42Promise = new Promise<ChatMessage[]>((resolve) => {
      resolveChat42 = resolve;
    });

    let resolveChat43!: (msgs: ChatMessage[]) => void;
    const chat43Promise = new Promise<ChatMessage[]>((resolve) => {
      resolveChat43 = resolve;
    });

    vi.mocked(chatApi.get).mockImplementation((id: number) => {
      if (id === 42) return chat42Promise;
      if (id === 43) return chat43Promise;
      return Promise.resolve([]);
    });

    const load42 = chatSessionActions.loadChat(42);
    const load43 = chatSessionActions.loadChat(43);

    resolveChat42([{ id: 1, role: "user", content: "Message from 42" }]);
    const result42 = await load42;

    expect(result42).toBe(false);
    expect(useChatStore.getState().activeChatId).not.toBe(42);

    resolveChat43([{ id: 2, role: "user", content: "Message from 43" }]);
    const result43 = await load43;

    expect(result43).toBe(true);
    expect(useChatStore.getState().activeChatId).toBe(43);
    expect(useChatStore.getState().messagesByChat[43]).toHaveLength(1);
  });

  it("clears chat loading state when request fails", async () => {
    vi.mocked(chatApi.get).mockRejectedValue(new Error("Network failure"));

    await expect(chatSessionActions.loadChat(99)).rejects.toThrow("Network failure");
    expect(useChatStore.getState().loadingChatIds[99]).toBeUndefined();
  });

  it("clears activeChat and invalidates hydration generation", () => {
    useChatStore.getState().setActiveChat(10);
    chatSessionActions.clearActiveChat();
    expect(useChatStore.getState().activeChatId).toBeNull();
  });

  it("creates a new chat and initializes store", async () => {
    vi.mocked(chatApi.create).mockResolvedValue({ chat_id: 88 });

    const newId = await chatSessionActions.createChat();

    expect(newId).toBe(88);
    expect(useChatStore.getState().messagesByChat[88]).toEqual([]);
    expect(useChatSessionStore.getState().sessions[0].id).toBe(88);
    expect(useChatSessionStore.getState().sessions[0].title).toBe("New Chat");
  });

  it("renames a chat successfully and updates local session", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 5,
          user_id: 1,
          title: "Initial Title",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
      ],
    });

    vi.mocked(chatApi.updateTitle).mockResolvedValue();

    await chatSessionActions.renameChat(5, "Renamed Title");

    expect(chatApi.updateTitle).toHaveBeenCalledWith(5, "Renamed Title");
    expect(useChatSessionStore.getState().sessions[0].title).toBe("Renamed Title");
    expect(useChatSessionStore.getState().mutatingChatIds[5]).toBeUndefined();
  });

  it("rejects empty title during rename", async () => {
    await expect(chatSessionActions.renameChat(5, "   ")).rejects.toThrow(
      "Chat title cannot be empty.",
    );
    expect(chatApi.updateTitle).not.toHaveBeenCalled();
  });

  it("deletes active chat, clears active state, and reports active status", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 42,
          user_id: 1,
          title: "Active Chat",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
      ],
    });
    useChatStore.getState().setActiveChat(42);
    useChatStore.getState().setMessages(42, [{ id: 1, role: "user", content: "Hi" }]);

    vi.mocked(chatApi.delete).mockResolvedValue();

    const wasActive = await chatSessionActions.deleteChat(42);

    expect(wasActive).toBe(true);
    expect(chatApi.delete).toHaveBeenCalledWith(42);
    expect(useChatSessionStore.getState().sessions).toHaveLength(0);
    expect(useChatStore.getState().activeChatId).toBeNull();
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();
  });

  it("deletes non-active chat without altering activeChatId", async () => {
    useChatSessionStore.setState({
      sessions: [
        {
          id: 10,
          user_id: 1,
          title: "Non Active Chat",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          has_pdf: false,
        },
      ],
    });
    useChatStore.getState().setActiveChat(99);

    vi.mocked(chatApi.delete).mockResolvedValue();

    const wasActive = await chatSessionActions.deleteChat(10);

    expect(wasActive).toBe(false);
    expect(useChatStore.getState().activeChatId).toBe(99);
    expect(useChatSessionStore.getState().sessions).toHaveLength(0);
  });
});