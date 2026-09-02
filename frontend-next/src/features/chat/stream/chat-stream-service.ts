import { ApiError } from "@/lib/errors/api-error";
import type { StreamPayload } from "@/types/api";

function getApiUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }
  return url;
}

export type ChatStreamEvent =
  | {
      type: "streamStarted";
    }
  | {
      type: "chunkReceived";
      chunk: string;
    }
  | {
      type: "streamCompleted";
    }
  | {
      type: "streamCancelled";
    }
  | {
      type: "streamFailed";
      error: ApiError;
    };

export interface ChatStreamHandlers {
  onEvent?: (event: ChatStreamEvent) => void;
}

export class ChatStreamService {
  private controller: AbortController | null = null;

  get isStreaming(): boolean {
    return this.controller !== null;
  }

  async stream(
    payload: StreamPayload,
    handlers: ChatStreamHandlers = {},
  ): Promise<void> {
    this.abort();

    const controller = new AbortController();
    this.controller = controller;

    handlers.onEvent?.({
      type: "streamStarted",
    });

    try {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("token")
          : null;

      const response = await fetch(
        `${getApiUrl().replace(/\/$/, "")}/chat/stream`,
        {
          method: "POST",
          headers: {
            Accept: "text/event-stream",
            "Content-Type": "application/json",
            ...(token
              ? {
                  Authorization: `Bearer ${token}`,
                }
              : {}),
          },
          body: JSON.stringify(payload),
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        const body = await this.readErrorBody(response);

        throw new ApiError(
          this.getErrorMessage(
            body,
            `Stream request failed with status ${response.status}.`,
          ),
          this.mapStatusToCode(response.status),
          response.status,
          body,
        );
      }

      if (!response.body) {
        throw new ApiError(
          "The server returned an empty stream.",
          "STREAM_ERROR",
          response.status,
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          if (controller.signal.aborted) {
            return;
          }

          const chunk = decoder.decode(value, {
            stream: true,
          });

          if (chunk) {
            handlers.onEvent?.({
              type: "chunkReceived",
              chunk,
            });
          }
        }

        const finalChunk = decoder.decode();

        if (finalChunk) {
          handlers.onEvent?.({
            type: "chunkReceived",
            chunk: finalChunk,
          });
        }

        if (!controller.signal.aborted) {
          handlers.onEvent?.({
            type: "streamCompleted",
          });
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      if (this.isAbortError(error) || controller.signal.aborted) {
        handlers.onEvent?.({
          type: "streamCancelled",
        });

        return;
      }

      const apiError =
        error instanceof ApiError
          ? error
          : new ApiError(
              "The AI stream failed.",
              "STREAM_ERROR",
              undefined,
              error,
            );

      handlers.onEvent?.({
        type: "streamFailed",
        error: apiError,
      });

      throw apiError;
    } finally {
      if (this.controller === controller) {
        this.controller = null;
      }
    }
  }

  abort(): void {
    if (!this.controller) {
      return;
    }

    this.controller.abort();
    this.controller = null;
  }

  private isAbortError(error: unknown): boolean {
    return (
      error instanceof DOMException && error.name === "AbortError"
    );
  }

  private async readErrorBody(response: Response): Promise<unknown> {
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      try {
        return await response.json();
      } catch {
        return null;
      }
    }

    try {
      return await response.text();
    } catch {
      return null;
    }
  }

  private getErrorMessage(body: unknown, fallback: string): string {
    if (typeof body === "string" && body.trim()) {
      return body;
    }

    if (typeof body === "object" && body !== null) {
      const data = body as Record<string, unknown>;

      if (typeof data.detail === "string") {
        return data.detail;
      }

      if (typeof data.message === "string") {
        return data.message;
      }

      if (typeof data.error === "string") {
        return data.error;
      }
    }

    return fallback;
  }

  private mapStatusToCode(status: number): string {
    switch (status) {
      case 401:
        return "UNAUTHORIZED";
      case 413:
        return "FILE_TOO_LARGE";
      case 429:
        return "RATE_LIMITED";
      case 502:
      case 503:
      case 504:
        return "PROVIDER_DOWN";
      default:
        return "STREAM_ERROR";
    }
  }
}

export const chatStreamService = new ChatStreamService();