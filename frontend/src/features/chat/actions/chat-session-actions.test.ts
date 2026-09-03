import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatSessionActions } from "./chat-session-actions";
import { chatApi } from "@/lib/api/chat";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
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

    // Ensure every test starts with a fresh hydration generation.
    chatSessionActions.invalidateHydration?.();

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
    expect(useChatStore.getState().messagesByChat[42]).toEqual(
      mockMessages,
    );
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("prevents a late A response from overwriting B during A -> B navigation", async () => {
    let resolveChatA!: (messages: ChatMessage[]) => void;
    const chatAPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveChatA = resolve;
    });

    let resolveChatB!: (messages: ChatMessage[]) => void;
    const chatBPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveChatB = resolve;
    });

    vi.mocked(chatApi.get).mockImplementation((chatId: number) => {
      if (chatId === 42) {
        return chatAPromise;
      }

      if (chatId === 43) {
        return chatBPromise;
      }

      return Promise.resolve([]);
    });

    const loadA = chatSessionActions.loadChat(42);
    const loadB = chatSessionActions.loadChat(43);

    resolveChatA([
      {
        id: 1,
        role: "user",
        content: "Message from A",
      },
    ]);

    const resultA = await loadA;

    expect(resultA).toBe(false);
    expect(useChatStore.getState().activeChatId).not.toBe(42);
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();

    resolveChatB([
      {
        id: 2,
        role: "user",
        content: "Message from B",
      },
    ]);

    const resultB = await loadB;

    expect(resultB).toBe(true);
    expect(useChatStore.getState().activeChatId).toBe(43);
    expect(useChatStore.getState().messagesByChat[43]).toEqual([
      {
        id: 2,
        role: "user",
        content: "Message from B",
      },
    ]);

    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();
  });

  it("survives a B -> A -> B rapid navigation race", async () => {
    let resolveFirstB!: (messages: ChatMessage[]) => void;
    const firstBPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveFirstB = resolve;
    });

    let resolveA!: (messages: ChatMessage[]) => void;
    const aPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveA = resolve;
    });

    let resolveSecondB!: (messages: ChatMessage[]) => void;
    const secondBPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveSecondB = resolve;
    });

    let bCallCount = 0;

    vi.mocked(chatApi.get).mockImplementation((chatId: number) => {
      if (chatId === 43) {
        bCallCount += 1;

        return bCallCount === 1
          ? firstBPromise
          : secondBPromise;
      }

      if (chatId === 42) {
        return aPromise;
      }

      return Promise.resolve([]);
    });

    const firstBLoad = chatSessionActions.loadChat(43);
    const aLoad = chatSessionActions.loadChat(42);
    const secondBLoad = chatSessionActions.loadChat(43);

    resolveFirstB([
      {
        id: 1,
        role: "user",
        content: "Old B response",
      },
    ]);

    const firstBResult = await firstBLoad;

    expect(firstBResult).toBe(false);
    expect(useChatStore.getState().activeChatId).not.toBe(43);
    expect(useChatStore.getState().messagesByChat[43]).toBeUndefined();

    resolveA([
      {
        id: 2,
        role: "user",
        content: "A response",
      },
    ]);

    const aResult = await aLoad;

    expect(aResult).toBe(false);
    expect(useChatStore.getState().activeChatId).not.toBe(42);
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();

    resolveSecondB([
      {
        id: 3,
        role: "user",
        content: "Latest B response",
      },
    ]);

    const secondBResult = await secondBLoad;

    expect(secondBResult).toBe(true);
    expect(useChatStore.getState().activeChatId).toBe(43);
    expect(useChatStore.getState().messagesByChat[43]).toEqual([
      {
        id: 3,
        role: "user",
        content: "Latest B response",
      },
    ]);
  });

  it("does not allow a stale hydration request to clear the loading state of the newer request", async () => {
    let resolveFirst!: (messages: ChatMessage[]) => void;
    const firstPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveFirst = resolve;
    });

    let resolveSecond!: (messages: ChatMessage[]) => void;
    const secondPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveSecond = resolve;
    });

    let callCount = 0;

    vi.mocked(chatApi.get).mockImplementation(() => {
      callCount += 1;

      return callCount === 1 ? firstPromise : secondPromise;
    });

    const firstLoad = chatSessionActions.loadChat(42);
    const secondLoad = chatSessionActions.loadChat(42);

    expect(useChatStore.getState().loadingChatIds[42]).toBe(true);

    resolveFirst([
      {
        id: 1,
        role: "user",
        content: "Old response",
      },
    ]);

    const firstResult = await firstLoad;

    expect(firstResult).toBe(false);
    expect(useChatStore.getState().loadingChatIds[42]).toBe(true);

    resolveSecond([
      {
        id: 2,
        role: "user",
        content: "Latest response",
      },
    ]);

    const secondResult = await secondLoad;

    expect(secondResult).toBe(true);
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
    expect(useChatStore.getState().messagesByChat[42]).toEqual([
      {
        id: 2,
        role: "user",
        content: "Latest response",
      },
    ]);
  });

  it("invalidates the active stream when chat hydration starts", async () => {
    const invalidateSpy = vi.spyOn(chatRequestController, "invalidate");

    let resolveChat!: (messages: ChatMessage[]) => void;

    const pendingChat = new Promise<ChatMessage[]>((resolve) => {
      resolveChat = resolve;
    });

    vi.mocked(chatApi.get).mockReturnValue(pendingChat);

    const loadPromise = chatSessionActions.loadChat(42);

    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().loadingChatIds[42]).toBe(true);

    resolveChat([]);

    const result = await loadPromise;

    expect(result).toBe(true);
    expect(useChatStore.getState().activeChatId).toBe(42);
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("does not resurrect a deleted chat when its pending hydration resolves late", async () => {
    const session: ChatSession = {
      id: 42,
      user_id: 1,
      title: "Chat To Delete",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      has_pdf: false,
    };

    useChatSessionStore.getState().setSessions([session]);

    useChatStore.getState().setActiveChat(42);
    useChatStore.getState().setMessages(42, [
      {
        id: 100,
        role: "user",
        content: "Existing message",
      },
    ]);

    let resolveLoad!: (messages: ChatMessage[]) => void;

    const pendingLoad = new Promise<ChatMessage[]>((resolve) => {
      resolveLoad = resolve;
    });

    vi.mocked(chatApi.get).mockReturnValue(pendingLoad);
    vi.mocked(chatApi.delete).mockResolvedValue();

    const loadPromise = chatSessionActions.loadChat(42);

    const deletePromise = chatSessionActions.deleteChat(42);

    await deletePromise;

    expect(useChatSessionStore.getState().sessions).toHaveLength(0);
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();
    expect(useChatStore.getState().activeChatId).toBeNull();

    resolveLoad([
      {
        id: 999,
        role: "user",
        content: "Deleted chat resurrected",
      },
    ]);

    const loadResult = await loadPromise;

    expect(loadResult).toBe(false);

    expect(useChatSessionStore.getState().sessions).toHaveLength(0);
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();
    expect(useChatStore.getState().activeChatId).toBeNull();
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("ignores a pending load when clearActiveChat is called", async () => {
    useChatStore.getState().setActiveChat(42);

    let resolveChat!: (messages: ChatMessage[]) => void;

    const pendingChat = new Promise<ChatMessage[]>((resolve) => {
      resolveChat = resolve;
    });

    vi.mocked(chatApi.get).mockReturnValue(pendingChat);

    const loadPromise = chatSessionActions.loadChat(42);

    expect(useChatStore.getState().loadingChatIds[42]).toBe(true);

    chatSessionActions.clearActiveChat();

    expect(useChatStore.getState().activeChatId).toBeNull();

    resolveChat([
      {
        id: 1,
        role: "user",
        content: "Late response",
      },
    ]);

    const result = await loadPromise;

    expect(result).toBe(false);
    expect(useChatStore.getState().activeChatId).toBeNull();
    expect(useChatStore.getState().messagesByChat[42]).toBeUndefined();
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("allows only the latest concurrent loadChat call for the same chat to win", async () => {
    let resolveFirst!: (messages: ChatMessage[]) => void;
    const firstPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveFirst = resolve;
    });

    let resolveSecond!: (messages: ChatMessage[]) => void;
    const secondPromise = new Promise<ChatMessage[]>((resolve) => {
      resolveSecond = resolve;
    });

    let callCount = 0;

    vi.mocked(chatApi.get).mockImplementation(() => {
      callCount += 1;

      return callCount === 1 ? firstPromise : secondPromise;
    });

    const firstLoad = chatSessionActions.loadChat(42);
    const secondLoad = chatSessionActions.loadChat(42);

    resolveSecond([
      {
        id: 2,
        role: "user",
        content: "Second request",
      },
    ]);

    const secondResult = await secondLoad;

    expect(secondResult).toBe(true);
    expect(useChatStore.getState().activeChatId).toBe(42);
    expect(useChatStore.getState().messagesByChat[42]).toEqual([
      {
        id: 2,
        role: "user",
        content: "Second request",
      },
    ]);
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();

    resolveFirst([
      {
        id: 1,
        role: "user",
        content: "First request",
      },
    ]);

    const firstResult = await firstLoad;

    expect(firstResult).toBe(false);

    expect(useChatStore.getState().activeChatId).toBe(42);
    expect(useChatStore.getState().messagesByChat[42]).toEqual([
      {
        id: 2,
        role: "user",
        content: "Second request",
      },
    ]);
    expect(useChatStore.getState().loadingChatIds[42]).toBeUndefined();
  });

  it("clears chat loading state when request fails", async () => {
    vi.mocked(chatApi.get).mockRejectedValue(
      new Error("Network failure"),
    );

    await expect(
      chatSessionActions.loadChat(99),
    ).rejects.toThrow("Network failure");

    expect(
      useChatStore.getState().loadingChatIds[99],
    ).toBeUndefined();
  });

  it("clears activeChat and invalidates hydration generation", () => {
    useChatStore.getState().setActiveChat(10);

    chatSessionActions.clearActiveChat();

    expect(useChatStore.getState().activeChatId).toBeNull();
  });

  it("creates a new chat and initializes store", async () => {
    vi.mocked(chatApi.create).mockResolvedValue({
      chat_id: 88,
    });

    const newId = await chatSessionActions.createChat();

    expect(newId).toBe(88);
    expect(useChatStore.getState().messagesByChat[88]).toEqual([]);
    expect(useChatSessionStore.getState().sessions[0].id).toBe(88);
    expect(useChatSessionStore.getState().sessions[0].title).toBe(
      "New Chat",
    );
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

    expect(chatApi.updateTitle).toHaveBeenCalledWith(
      5,
      "Renamed Title",
    );
    expect(
      useChatSessionStore.getState().sessions[0].title,
    ).toBe("Renamed Title");
    expect(
      useChatSessionStore.getState().mutatingChatIds[5],
    ).toBeUndefined();
  });

  it("rejects empty title during rename", async () => {
    await expect(
      chatSessionActions.renameChat(5, "   "),
    ).rejects.toThrow("Chat title cannot be empty.");

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
    useChatStore.getState().setMessages(42, [
      {
        id: 1,
        role: "user",
        content: "Hi",
      },
    ]);

    vi.mocked(chatApi.delete).mockResolvedValue();

    const wasActive = await chatSessionActions.deleteChat(42);

    expect(wasActive).toBe(true);
    expect(chatApi.delete).toHaveBeenCalledWith(42);
    expect(useChatSessionStore.getState().sessions).toHaveLength(0);
    expect(useChatStore.getState().activeChatId).toBeNull();
    expect(
      useChatStore.getState().messagesByChat[42],
    ).toBeUndefined();
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