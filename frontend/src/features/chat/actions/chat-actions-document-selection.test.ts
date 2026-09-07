import { describe, expect, it } from "vitest";

import {
  buildStreamPayload,
} from "./chat-actions";

describe("chat stream document selection payload", () => {
  const baseOptions = {
    chatId: 10,
    prompt: "Explain the document",
    model: "gemini-2.5-flash" as const,
    provider: "gemini" as const,
  };

  it("includes document_id when a document is selected", () => {
    const payload = buildStreamPayload(
      baseOptions,
      42,
    );

    expect(payload).toEqual({
      chat_id: 10,
      prompt: "Explain the document",
      model: "gemini-2.5-flash",
      provider: "gemini",
      document_id: 42,
    });
  });

  it("omits document_id when no document is selected", () => {
    const payload = buildStreamPayload(
      baseOptions,
      null,
    );

    expect(payload).toEqual({
      chat_id: 10,
      prompt: "Explain the document",
      model: "gemini-2.5-flash",
      provider: "gemini",
    });

    expect(
      Object.prototype.hasOwnProperty.call(
        payload,
        "document_id",
      ),
    ).toBe(false);
  });

  it("trims the prompt before generating the stream payload", () => {
    const payload = buildStreamPayload(
      {
        ...baseOptions,
        prompt: "  Explain the document  ",
      },
      42,
    );

    expect(payload.prompt).toBe(
      "Explain the document",
    );
    expect(payload.document_id).toBe(42);
  });

  it("preserves image payload fields", () => {
    const payload = buildStreamPayload(
      {
        ...baseOptions,
        imageBase64: ["base64-image"],
        imageMime: ["image/png"],
      },
      42,
    );

    expect(payload).toMatchObject({
      image_base64: ["base64-image"],
      image_mime: ["image/png"],
      document_id: 42,
    });
  });
});