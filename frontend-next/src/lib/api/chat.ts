import { apiClient } from "@/lib/api/client";
import type {
  ChatDetailsResponse,
  ChatMessage,
  ChatSession,
  StreamPayload,
  UploadPdfResponse,
} from "@/types/api";

export const chatApi = {
  getAll(): Promise<ChatSession[]> {
    return apiClient.get<ChatSession[]>("/chat/all");
  },

  create(): Promise<ChatSession> {
    return apiClient.post<ChatSession>("/chat/new");
  },

  get(chatId: number): Promise<ChatMessage[]> {
    return apiClient.get<ChatMessage[]>(`/chat/${chatId}`);
  },

  getDetails(chatId: number): Promise<ChatDetailsResponse> {
    return apiClient.get<ChatDetailsResponse>(
      `/chat/details/${chatId}`,
    );
  },

  delete(chatId: number): Promise<void> {
    return apiClient.delete<void>(`/chat/${chatId}`);
  },

  updateTitle(chatId: number, title: string): Promise<void> {
    const params = new URLSearchParams({
      new_title: title,
    });

    return apiClient.put<void>(
      `/chat/${chatId}/title?${params.toString()}`,
    );
  },

  uploadPdf(
    chatId: number,
    file: File,
  ): Promise<UploadPdfResponse> {
    const formData = new FormData();
    formData.append("file", file);

    return apiClient.post<UploadPdfResponse>(
      `/chat/upload-pdf/${chatId}`,
      formData,
    );
  },

  cleanup(chatId: number, index: number): Promise<void> {
    return apiClient.delete<void>(
      `/chat/${chatId}/cleanup/${index}`,
    );
  },

  /**
   * Streaming is intentionally NOT implemented here.
   *
   * `/chat/stream` belongs to chatStreamService because it has
   * AbortController + ReadableStream lifecycle semantics.
   */
  stream(_payload: StreamPayload): never {
    throw new Error(
      "Use chatStreamService for /chat/stream instead.",
    );
  },
};