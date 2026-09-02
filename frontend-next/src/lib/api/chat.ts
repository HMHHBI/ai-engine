import { apiClient } from "@/lib/api/client";
import type { ChatMessage, ChatSession } from "@/types/api";

export interface CreateChatResponse {
  chat_id: number;
}

export interface UploadPdfResponse {
  filename: string;
  chunks_count: number;
}

export const chatApi = {
  getAll(): Promise<ChatSession[]> {
    return apiClient.get<ChatSession[]>("/chat/all");
  },

  create(): Promise<CreateChatResponse> {
    return apiClient.post<CreateChatResponse>("/chat/new");
  },

  get(chatId: number): Promise<ChatMessage[]> {
    return apiClient.get<ChatMessage[]>(`/chat/${chatId}`);
  },

  updateTitle(chatId: number, title: string): Promise<ChatSession> {
    return apiClient.put<ChatSession>(`/chat/${chatId}/title`, { title });
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