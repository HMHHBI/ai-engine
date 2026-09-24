import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ResearchWorkspace } from "./research-workspace";
import { useWorkspaceUiStore } from "../store/workspace-ui-store";
import type { Document } from "@/types/api";

vi.mock("@/features/chat/components/chat-area", () => ({
  ChatArea: () => <div data-testid="mocked-chat-area">Chat Area Content</div>,
}));

describe("ResearchWorkspace Responsive Fallback (M4.6)", () => {
  const mockDoc: Document = {
    id: 101,
    user_id: 1,
    chat_id: 1,
    filename: "test_research.pdf",
    mime_type: "application/pdf",
    file_size: 2048,
    page_count: 3,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
  };

  beforeEach(() => {
    useWorkspaceUiStore.getState().resetUiState();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("R1: renders two-pane split on wide viewport", () => {
    window.innerWidth = 1280;
    render(<ResearchWorkspace document={mockDoc} />);

    expect(screen.getByTestId("workspace-chat-pane")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-document-pane-container")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-resize-handle")).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-responsive-drawer")).not.toBeInTheDocument();
  });

  it("R2: renders single chat pane without compressed second column on narrow viewport when collapsed", () => {
    window.innerWidth = 640;
    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(true);

    render(<ResearchWorkspace document={mockDoc} />);

    expect(screen.getByTestId("workspace-chat-pane")).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-document-pane-container")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-resize-handle")).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-reopen-document-button")).toBeInTheDocument();
  });

  it("R3: opens responsive drawer when document is active on narrow viewport", () => {
    window.innerWidth = 640;
    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(false);

    render(<ResearchWorkspace document={mockDoc} />);

    expect(screen.getByTestId("workspace-responsive-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-document-pane")).toBeInTheDocument();
    expect(screen.getAllByText("test_research.pdf")[0]).toBeInTheDocument();
  });

  it("R4: closing responsive pane collapses the drawer but leaves workspace intact", () => {
    window.innerWidth = 640;
    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(false);
    const mockOnClose = vi.fn();

    render(<ResearchWorkspace document={mockDoc} onClose={mockOnClose} />);

    const closeBtn = screen.getByTestId("workspace-close-button");
    fireEvent.click(closeBtn);

    // Collapsed in store, so drawer closes without calling parent full onClose
    expect(useWorkspaceUiStore.getState().isDocumentPaneCollapsed).toBe(true);
    expect(mockOnClose).not.toHaveBeenCalled();
  });

  it("R5: closing on desktop invokes the parent onClose handler to clear URL parameter", () => {
    window.innerWidth = 1280;
    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(false);
    const mockOnClose = vi.fn();

    render(<ResearchWorkspace document={mockDoc} onClose={mockOnClose} />);

    const closeBtn = screen.getByTestId("workspace-close-button");
    fireEvent.click(closeBtn);

    expect(mockOnClose).toHaveBeenCalled();
  });
});
