import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResearchWorkspace } from "./research-workspace";
import type { Document } from "@/types/api";

vi.mock("@/features/chat/components/chat-area", () => ({
  ChatArea: () => <div data-testid="mocked-chat-area">Chat Area Content</div>,
}));

describe("ResearchWorkspace (M4.4)", () => {
  const mockDoc: Document = {
    id: 101,
    user_id: 1,
    chat_id: 1,
    filename: "spec.pdf",
    mime_type: "application/pdf",
    file_size: 2048,
    page_count: 3,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };

  it("renders both chat pane and document pane in desktop split layout", () => {
    render(<ResearchWorkspace document={mockDoc} />);

    expect(screen.getByTestId("workspace-split-pane")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-chat-pane")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-document-pane")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-resize-handle")).toBeInTheDocument();
    expect(screen.getByText("spec.pdf")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-viewer-boundary")).toBeInTheDocument();
  });

  it("enforces minimum width on chat pane container", () => {
    render(<ResearchWorkspace document={mockDoc} />);
    const chatPane = screen.getByTestId("workspace-chat-pane");
    expect(chatPane).toHaveStyle({ minWidth: "420px" });
  });
});
