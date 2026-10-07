import { chatApi } from "@/lib/api/chat";
import { documentApi } from "@/lib/api/documents";
import { chatRequestController } from "@/features/chat/stream/chat-request-controller";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { useDocumentStore } from "@/features/documents/document-store";
import type {
  ChatMessage,
  ChatPersona,
  ChatSession,
} from "@/types/api";

function normalizeMessages(messages: ChatMessage[]): ChatMessage[] {
  return (messages || []).map((message) => ({
    ...message,
    content: message.content ?? message.text ?? "",
    sources:
      Array.isArray(message.sources) && message.sources.length > 0
        ? message.sources
        : undefined,
  }));
}

function getLatestReadyDocumentId(
  documents: {
    id: number;
    status: string;
    updated_at: string;
  }[],
): number | null {
  const readyDocuments = documents
    .filter((document) => document.status === "ready")
    .sort((a, b) => {
      const timestampDifference =
        new Date(b.updated_at).getTime() -
        new Date(a.updated_at).getTime();

      if (timestampDifference !== 0) {
        return timestampDifference;
      }

      return b.id - a.id;
    });

  return readyDocuments[0]?.id ?? null;
}

class ChatSessionActions {
  private hydrationGeneration = 0;

  async loadChats(): Promise<void> {
    const sessionStore = useChatSessionStore.getState();

    sessionStore.setLoading(true);
    sessionStore.setError(null);

    try {
      const sessions = await chatApi.getAll();

      const sortedSessions = [...sessions].sort((a, b) => {
        const aTime = a.last_active_at
          ? new Date(a.last_active_at).getTime()
          : new Date(a.updated_at).getTime();

        const bTime = b.last_active_at
          ? new Date(b.last_active_at).getTime()
          : new Date(b.updated_at).getTime();

        return bTime - aTime;
      });

      useChatSessionStore.getState().setSessions(sortedSessions);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to load chat history.";

      useChatSessionStore.getState().setError(message);
      throw error;
    } finally {
      useChatSessionStore.getState().setLoading(false);
    }
  }

  async createChat(): Promise<number> {
    const response = await chatApi.create();
    const chatId = Number(
      (response as { id?: number; chat_id?: number }).id ??
        (response as { id?: number; chat_id?: number }).chat_id,
    );
    const now = new Date().toISOString();

    const session: ChatSession = {
      id: chatId,
      user_id: 0,
      title: "New Chat",
      created_at: now,
      updated_at: now,
      has_pdf: false,
      persona: "default",
      custom_instructions: null,
      attached_documents_count: 0,
      primary_document_title: null,
      message_count: 0,
      last_active_at: null,
    };

    useChatStore.getState().setMessages(chatId, []);
    useDocumentStore
      .getState()
      .hydrateChatDocuments(chatId, [], null);

    useChatSessionStore.getState().addSession(session);

    return chatId;
  }

  syncFirstMessageTitle(
    chatId: number,
    prompt: string,
  ): void {
    const sessionStore = useChatSessionStore.getState();
    const documentStore = useDocumentStore.getState();

    const session = sessionStore.sessions.find(
      (item) => item.id === chatId,
    );

    if (
      !session ||
      session.title !== "New Chat"
    ) {
      return;
    }

    const documents =
      documentStore.documentsByChat[chatId] ?? [];

    const latestReadyDocument = [...documents]
      .filter((document) => document.status === "ready")
      .sort((a, b) => {
        const timestampDifference =
          new Date(b.updated_at).getTime() -
          new Date(a.updated_at).getTime();

        if (timestampDifference !== 0) {
          return timestampDifference;
        }

        return b.id - a.id;
      })[0];

    if (latestReadyDocument) {
      sessionStore.promoteSession(chatId, {
        title: latestReadyDocument.filename.replace(
          /\.[^.]+$/,
          "",
        ).replace(/[_-]+/g, " ").trim(),
        primary_document_title:
          latestReadyDocument.filename,
        attached_documents_count: documents.length,
        updated_at: new Date().toISOString(),
      });

      return;
    }

    const normalizedPrompt = prompt.trim();

    if (!normalizedPrompt) {
      return;
    }

    const title =
      normalizedPrompt.length > 80
        ? `${normalizedPrompt.slice(0, 77).trimEnd()}...`
        : normalizedPrompt.replace(/[?!.]+$/, "");

    sessionStore.promoteSession(chatId, {
      title,
      updated_at: new Date().toISOString(),
    });
  }

  async renameChat(
    chatId: number,
    title: string,
  ): Promise<void> {
    const normalizedTitle = title.trim();

    if (!normalizedTitle) {
      throw new Error("Chat title cannot be empty.");
    }

    const sessionStore = useChatSessionStore.getState();

    sessionStore.setChatMutating(chatId, true);

    try {
      await chatApi.updateTitle(
        chatId,
        normalizedTitle,
      );

      useChatSessionStore.getState().updateSession(
        chatId,
        {
          title: normalizedTitle,
          updated_at: new Date().toISOString(),
        },
      );
    } finally {
      useChatSessionStore
        .getState()
        .setChatMutating(chatId, false);
    }
  }

  async updatePersona(
    chatId: number,
    persona: ChatPersona,
    customInstructions: string,
  ): Promise<ChatSession> {
    const normalizedInstructions =
      customInstructions.trim();

    const updatedChat =
      await chatApi.updatePersona(chatId, {
        persona,
        custom_instructions:
          normalizedInstructions.length > 0
            ? normalizedInstructions
            : null,
      });

    useChatSessionStore.getState().updateSession(
      chatId,
      {
        persona: updatedChat.persona,
        custom_instructions:
          updatedChat.custom_instructions,
        updated_at: new Date().toISOString(),
      },
    );

    return updatedChat;
  }

  async deleteChat(
    chatId: number,
  ): Promise<boolean> {
    const wasActive =
      useChatStore.getState().activeChatId === chatId;

    const sessionStore =
      useChatSessionStore.getState();

    sessionStore.setChatMutating(
      chatId,
      true,
    );

    try {
      chatRequestController.invalidate();
      this.invalidateHydration();

      await chatApi.delete(chatId);

      useChatSessionStore
        .getState()
        .removeSession(chatId);

      useChatStore
        .getState()
        .removeChat(chatId);

      const documentStore =
        useDocumentStore.getState();

      documentStore.hydrateChatDocuments(
        chatId,
        [],
        null,
      );

      if (wasActive) {
        this.clearActiveChat();
      }

      return wasActive;
    } finally {
      useChatSessionStore
        .getState()
        .setChatMutating(
          chatId,
          false,
        );
    }
  }

  async hydrateSession(
    chatId: number,
  ): Promise<boolean> {
    chatRequestController.invalidate();

    const generation =
      ++this.hydrationGeneration;

    const previousChatId =
      useChatStore.getState().activeChatId;

    if (previousChatId !== null) {
      useChatStore
        .getState()
        .setChatLoading(
          previousChatId,
          false,
        );

      useDocumentStore
        .getState()
        .clearSelectedDocument(
          previousChatId,
        );
    }

    useChatStore
      .getState()
      .setActiveChat(null);

    useChatStore
      .getState()
      .setChatLoading(
        chatId,
        true,
      );

    try {
      const detailsPromise =
        typeof chatApi.getDetails === "function"
          ? Promise.resolve().then(() => chatApi.getDetails(chatId)).catch(() => null)
          : Promise.resolve(null);

      const docsPromise =
        typeof documentApi?.listForChat === "function"
          ? Promise.resolve().then(() => documentApi.listForChat(chatId)).catch(() => [])
          : Promise.resolve([]);

      const [
        sessionDetails,
        rawMessages,
        documents,
      ] = await Promise.all([
        detailsPromise,
        chatApi.get(chatId),
        docsPromise,
      ]);

      if (
        generation !== this.hydrationGeneration
      ) {
        return false;
      }

      const normalizedMessages =
        normalizeMessages(rawMessages);

      const primaryDocumentId =
        getLatestReadyDocumentId(documents);

      if (sessionDetails) {
        useChatSessionStore
          .getState()
          .updateSession(
            chatId,
            {
              id: sessionDetails.id,
              title: sessionDetails.title,
              persona: sessionDetails.persona,
              custom_instructions:
                sessionDetails.custom_instructions,
              attached_documents_count:
                sessionDetails.attached_documents_count,
              primary_document_title:
                sessionDetails.primary_document_title,
              message_count:
                sessionDetails.message_count,
              last_active_at:
                sessionDetails.last_active_at,
              created_at:
                sessionDetails.created_at,
              updated_at:
                sessionDetails.updated_at,
            },
          );
      }

      useChatStore
        .getState()
        .setMessages(
          chatId,
          normalizedMessages,
        );

      useDocumentStore
        .getState()
        .hydrateChatDocuments(
          chatId,
          documents,
          primaryDocumentId,
        );

      useChatStore
        .getState()
        .setActiveChat(chatId);

      return true;
    } finally {
      if (
        generation ===
        this.hydrationGeneration
      ) {
        useChatStore
          .getState()
          .setChatLoading(
            chatId,
            false,
          );
      }
    }
  }

  async loadChat(
    chatId: number,
  ): Promise<boolean> {
    return this.hydrateSession(chatId);
  }

  invalidateHydration(): void {
    this.hydrationGeneration += 1;
  }

  clearActiveChat(): void {
    const store = useChatStore.getState();
    const activeChatId = store.activeChatId;

    chatRequestController.invalidate();
    this.invalidateHydration();

    Object.keys(store.loadingChatIds).forEach((id) => {
      store.setChatLoading(Number(id), false);
    });

    if (activeChatId !== null) {
      useDocumentStore
        .getState()
        .clearSelectedDocument(
          activeChatId,
        );
    }

    useChatStore
      .getState()
      .setActiveChat(null);
  }
}

export const chatSessionActions =
  new ChatSessionActions();
