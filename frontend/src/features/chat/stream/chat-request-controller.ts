import { chatStreamService } from "@/features/chat/stream/chat-stream-service";

class ChatRequestController {
  private requestId = 0;

  next(): number {
    this.requestId += 1;
    chatStreamService.abort();
    return this.requestId;
  }

  invalidate(): void {
    this.requestId += 1;
    chatStreamService.abort();
  }

  isCurrent(requestId: number): boolean {
    return this.requestId === requestId;
  }

  cancelChat(chatId: number): void {
    if (chatStreamService.currentChatId !== chatId) {
      return;
    }
    this.invalidate();
  }
}

export const chatRequestController = new ChatRequestController();