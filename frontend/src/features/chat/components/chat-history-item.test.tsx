import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ChatHistoryItem } from "./chat-history-item";
import type { ChatSession } from "@/types/api";

function createSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: 42,
    user_id: 1,
    title: "Attention Is All You Need",
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-06T10:00:00Z",
    has_pdf: true,
    persona: "academic",
    custom_instructions: null,
    attached_documents_count: 2,
    primary_document_title: "Attention Is All You Need.pdf",
    message_count: 14,
    last_active_at: "2026-10-06T10:00:00Z",
    ...overrides,
  };
}

describe("ChatHistoryItem", () => {
  it("renders research session metadata", () => {
    render(
      <ChatHistoryItem
        session={createSession()}
        isActive={false}
        isMutating={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDeleteRequest={vi.fn()}
      />,
    );

    expect(screen.getByText("Attention Is All You Need")).toBeInTheDocument();

    expect(screen.getByText("2 docs")).toBeInTheDocument();

    expect(screen.getByText("Academic")).toBeInTheDocument();

    expect(screen.getByText(/Active/)).toBeInTheDocument();
  });

  it("renders the primary document when exactly one document exists", () => {
    render(
      <ChatHistoryItem
        session={createSession({
          attached_documents_count: 1,
        })}
        isActive={false}
        isMutating={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDeleteRequest={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Attention Is All You Need.pdf"),
    ).toBeInTheDocument();
  });

  it("renders a clean fallback for zero-document sessions", () => {
    render(
      <ChatHistoryItem
        session={createSession({
          attached_documents_count: 0,
          primary_document_title: null,
        })}
        isActive={false}
        isMutating={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDeleteRequest={vi.fn()}
      />,
    );

    expect(screen.getByText("Research session")).toBeInTheDocument();
  });

  it("renders the configured persona", () => {
    render(
      <ChatHistoryItem
        session={createSession({
          persona: "developer",
        })}
        isActive={false}
        isMutating={false}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onDeleteRequest={vi.fn()}
      />,
    );

    expect(screen.getByText("Developer")).toBeInTheDocument();
  });
});
