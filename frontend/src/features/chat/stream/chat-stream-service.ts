import { ApiError } from "@/lib/errors/api-error";
import type {
  AIModel,
  AIProvider,
  RetrievedSource,
  StreamPayload,
} from "@/types/api";

function getApiUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;

  if (!url) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  return url;
}

interface StreamStartedData {
  provider?: AIProvider;
  model?: AIModel;
}

interface SourcesReceivedData {
  sources?: RetrievedSource[];
}

interface ChunkReceivedData {
  text?: string;
}

interface StreamCompletedData {
  message_id?: number;
}

interface StreamCancelledData {
  message?: string;
}

interface StreamFailedData {
  code?: string;
  message?: string;
}

export type ChatStreamEvent =
  | {
      type: "streamStarted";
      provider?: AIProvider;
      model?: AIModel;
    }
  | {
      type: "sourcesReceived";
      sources: RetrievedSource[];
    }
  | {
      type: "chunkReceived";
      chunk: string;
    }
  | {
      type: "streamCompleted";
      messageId?: number;
    }
  | {
      type: "streamCancelled";
      message?: string;
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
  private activeStreamId = 0;
  private activeChatId: number | null = null;

  get isStreaming(): boolean {
    return this.controller !== null;
  }

  get currentChatId(): number | null {
    return this.activeChatId;
  }

  get currentStreamId(): number {
    return this.activeStreamId;
  }

  async stream(
    payload: StreamPayload,
    handlers: ChatStreamHandlers = {},
  ): Promise<void> {
    this.abort();

    const controller = new AbortController();
    const streamId = ++this.activeStreamId;

    this.controller = controller;
    this.activeChatId = payload.chat_id;

    const isCurrentStream = (): boolean =>
      this.activeStreamId === streamId &&
      this.controller === controller &&
      this.activeChatId === payload.chat_id &&
      !controller.signal.aborted;

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

      let buffer = "";
      let receivedCompletionEvent = false;
      let receivedCancellationEvent = false;

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          if (!isCurrentStream()) {
            return;
          }

          buffer += decoder.decode(value, {
            stream: true,
          });

          buffer = this.processSseBuffer(
            buffer,
            handlers,
            isCurrentStream,
            (eventName) => {
              if (eventName === "stream_completed") {
                receivedCompletionEvent = true;
              }

              if (eventName === "stream_cancelled") {
                receivedCancellationEvent = true;
              }
            },
          );

          if (
            receivedCompletionEvent ||
            receivedCancellationEvent
          ) {
            break;
          }
        }

        buffer += decoder.decode();

        if (
          isCurrentStream() &&
          !receivedCancellationEvent
        ) {
          this.processSseBuffer(
            buffer,
            handlers,
            isCurrentStream,
            (eventName) => {
              if (eventName === "stream_completed") {
                receivedCompletionEvent = true;
              }

              if (eventName === "stream_cancelled") {
                receivedCancellationEvent = true;
              }
            },
            true,
          );
        }

        if (
          isCurrentStream() &&
          !receivedCompletionEvent &&
          !receivedCancellationEvent
        ) {
          handlers.onEvent?.({
            type: "streamCompleted",
          });
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      if (
        this.isAbortError(error) ||
        controller.signal.aborted
      ) {
        handlers.onEvent?.({
          type: "streamCancelled",
        });

        throw new ApiError(
          "The AI stream was cancelled.",
          "STREAM_ABORTED",
          undefined,
          error,
        );
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

      if (isCurrentStream()) {
        handlers.onEvent?.({
          type: "streamFailed",
          error: apiError,
        });
      }

      throw apiError;
    } finally {
      if (this.controller === controller) {
        this.controller = null;
        this.activeChatId = null;
      }
    }
  }

  abort(): void {
    this.activeStreamId += 1;

    const controller = this.controller;

    this.controller = null;
    this.activeChatId = null;

    controller?.abort();
  }

  abortChat(chatId: number): void {
    if (this.activeChatId !== chatId) {
      return;
    }

    this.abort();
  }

  private processSseBuffer(
    buffer: string,
    handlers: ChatStreamHandlers,
    isCurrentStream: () => boolean,
    onEventName: (eventName: string) => void,
    flush = false,
  ): string {
    const normalized = buffer
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n");

    const separator = "\n\n";

    if (flush) {
      const finalEvent = normalized.trim();

      if (
        finalEvent &&
        isCurrentStream()
      ) {
        const eventName =
          this.getSseEventName(finalEvent);

        if (eventName) {
          onEventName(eventName);
        }

        this.processSseEvent(
          finalEvent,
          handlers,
          isCurrentStream,
        );
      }

      return "";
    }

    let working = normalized;

    while (true) {
      const separatorIndex =
        working.indexOf(separator);

      if (separatorIndex === -1) {
        break;
      }

      const rawEvent = working.slice(
        0,
        separatorIndex,
      );

      working = working.slice(
        separatorIndex + separator.length,
      );

      if (
        rawEvent.trim() &&
        isCurrentStream()
      ) {
        const eventName =
          this.getSseEventName(rawEvent);

        if (eventName) {
          onEventName(eventName);
        }

        this.processSseEvent(
          rawEvent,
          handlers,
          isCurrentStream,
        );
      }
    }

    return working;
  }

  private getSseEventName(
    rawEvent: string,
  ): string | null {
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        return line
          .slice("event:".length)
          .trim();
      }
    }

    return null;
  }

  private processSseEvent(
    rawEvent: string,
    handlers: ChatStreamHandlers,
    isCurrentStream: () => boolean,
  ): void {
    let eventName = "";
    const dataLines: string[] = [];

    for (const line of rawEvent.split("\n")) {
      if (line.startsWith(":")) {
        continue;
      }

      if (line.startsWith("event:")) {
        eventName = line
          .slice("event:".length)
          .trim();

        continue;
      }

      if (line.startsWith("data:")) {
        dataLines.push(
          line
            .slice("data:".length)
            .trimStart(),
        );
      }
    }

    if (
      !eventName ||
      dataLines.length === 0
    ) {
      return;
    }

    const dataText =
      dataLines.join("\n");

    let data: unknown;

    try {
      data = JSON.parse(dataText);
    } catch {
      const error = new ApiError(
        "The server returned an invalid stream event.",
        "STREAM_ERROR",
        undefined,
        {
          event: eventName,
          data: dataText,
        },
      );

      if (isCurrentStream()) {
        handlers.onEvent?.({
          type: "streamFailed",
          error,
        });
      }

      return;
    }

    this.dispatchSseEvent(
      eventName,
      data,
      handlers,
      isCurrentStream,
    );
  }

  private dispatchSseEvent(
    eventName: string,
    data: unknown,
    handlers: ChatStreamHandlers,
    isCurrentStream: () => boolean,
  ): void {
    if (!isCurrentStream()) {
      return;
    }

    switch (eventName) {
      case "stream_started": {
        const eventData =
          this.asRecord<StreamStartedData>(
            data,
          );

        handlers.onEvent?.({
          type: "streamStarted",
          provider:
            this.asAIProvider(
              eventData.provider,
            ),
          model:
            this.asAIModel(
              eventData.model,
            ),
        });

        break;
      }

      case "sources": {
        const eventData =
          this.asRecord<SourcesReceivedData>(
            data,
          );

        const sources =
          Array.isArray(
            eventData.sources,
          )
            ? eventData.sources.filter(
                (
                  source,
                ): source is RetrievedSource =>
                  this.isRetrievedSource(
                    source,
                  ),
              )
            : [];

        handlers.onEvent?.({
          type: "sourcesReceived",
          sources,
        });

        break;
      }

      case "chunk": {
        const eventData =
          this.asRecord<ChunkReceivedData>(
            data,
          );

        if (
          typeof eventData.text ===
          "string"
        ) {
          handlers.onEvent?.({
            type: "chunkReceived",
            chunk: eventData.text,
          });
        }

        break;
      }

      case "stream_completed": {
        const eventData =
          this.asRecord<StreamCompletedData>(
            data,
          );

        handlers.onEvent?.({
          type: "streamCompleted",
          messageId:
            typeof eventData.message_id ===
            "number"
              ? eventData.message_id
              : undefined,
        });

        break;
      }

      case "stream_cancelled": {
        const eventData =
          this.asRecord<StreamCancelledData>(
            data,
          );

        handlers.onEvent?.({
          type: "streamCancelled",
          message:
            typeof eventData.message ===
            "string"
              ? eventData.message
              : undefined,
        });

        break;
      }

      case "stream_error": {
        const eventData =
          this.asRecord<StreamFailedData>(
            data,
          );

        const error =
          new ApiError(
            typeof eventData.message ===
              "string"
              ? eventData.message
              : "The AI stream failed.",
            typeof eventData.code ===
              "string"
              ? eventData.code
              : "STREAM_ERROR",
            undefined,
            data,
            true,
          );

        handlers.onEvent?.({
          type: "streamFailed",
          error,
        });

        break;
      }

      default:
        break;
    }
  }

  private asRecord<T>(
    value: unknown,
  ): T & Record<string, unknown> {
    if (
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    ) {
      return value as T &
        Record<string, unknown>;
    }

    return {} as T &
      Record<string, unknown>;
  }

  private isRetrievedSource(
    value: unknown,
  ): value is RetrievedSource {
    if (
      typeof value !== "object" ||
      value === null ||
      Array.isArray(value)
    ) {
      return false;
    }

    const source =
      value as Record<
        string,
        unknown
      >;

    return (
      typeof source.id === "number" &&
      (source.page_number === null ||
        typeof source.page_number ===
          "number") &&
      (source.chunk_index === null ||
        typeof source.chunk_index ===
          "number") &&
      typeof source.distance ===
        "number"
    );
  }

  private asAIProvider(
    value: unknown,
  ): AIProvider | undefined {
    if (
      value === "gemini" ||
      value === "ollama" ||
      value === "openai"
    ) {
      return value;
    }

    return undefined;
  }

  private asAIModel(
    value: unknown,
  ): AIModel | undefined {
    if (
      value === "gemini-2.5-flash" ||
      value === "llama3.2" ||
      value === "deepseek-r1" ||
      value === "gpt-4o-mini"
    ) {
      return value;
    }

    return undefined;
  }

  private isAbortError(
    error: unknown,
  ): boolean {
    return (
      error instanceof DOMException &&
      error.name === "AbortError"
    );
  }

  private async readErrorBody(
    response: Response,
  ): Promise<unknown> {
    const contentType =
      response.headers.get(
        "content-type",
      ) ?? "";

    if (
      contentType.includes(
        "application/json",
      )
    ) {
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

  private getErrorMessage(
    body: unknown,
    fallback: string,
  ): string {
    if (
      typeof body === "string" &&
      body.trim()
    ) {
      return body;
    }

    if (
      typeof body === "object" &&
      body !== null
    ) {
      const data =
        body as Record<
          string,
          unknown
        >;

      if (
        typeof data.detail ===
        "string"
      ) {
        return data.detail;
      }

      if (
        typeof data.message ===
        "string"
      ) {
        return data.message;
      }

      if (
        typeof data.error ===
        "string"
      ) {
        return data.error;
      }
    }

    return fallback;
  }

  private mapStatusToCode(
    status: number,
  ): string {
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

export const chatStreamService =
  new ChatStreamService();