import { apiClient } from "@/lib/api/client";
import type {
  ChatDetailsResponse,
  ChatMessage,
  ChatPersonaUpdate,
  ChatSession,
} from "@/types/api";

export interface CreateChatResponse {
  chat_id: number;
}

export interface UploadPdfResponse {
  filename: string;
  chunks_count: number;
}

function normalizeChatMessage(message: ChatMessage): ChatMessage {
  return {
    ...message,
    content: message.content ?? message.text ?? "",
    sources:
      Array.isArray(message.sources) && message.sources.length > 0
        ? message.sources
        : undefined,
  };
}

export const chatApi = {
  getAll(): Promise<ChatSession[]> {
    return apiClient.get<ChatSession[]>("/chat/all");
  },

  create(): Promise<CreateChatResponse> {
    return apiClient.post<CreateChatResponse>("/chat/new");
  },

  get(chatId: number): Promise<ChatMessage[]> {
    return apiClient
      .get<ChatMessage[]>(`/chat/${chatId}`)
      .then((messages) => (messages || []).map(normalizeChatMessage));
  },

  getDetails(chatId: number): Promise<ChatDetailsResponse> {
    return apiClient.get<ChatDetailsResponse>(`/chat/details/${chatId}`);
  },

  updatePersona(
    chatId: number,
    payload: ChatPersonaUpdate,
  ): Promise<ChatSession> {
    return apiClient.patch<ChatSession>(`/chat/${chatId}/persona`, payload);
  },

  updateTitle(chatId: number, title: string): Promise<void> {
    const params = new URLSearchParams({ new_title: title });
    return apiClient.put<void>(`/chat/${chatId}/title?${params.toString()}`);
  },

  delete(chatId: number): Promise<void> {
    return apiClient.delete<void>(`/chat/${chatId}`);
  },

  uploadPdf(chatId: number, file: File): Promise<UploadPdfResponse> {
    const formData = new FormData();
    formData.append("file", file);

    return apiClient.post<UploadPdfResponse>(
      `/chat/upload-pdf/${chatId}`,
      formData,
    );
  },
};