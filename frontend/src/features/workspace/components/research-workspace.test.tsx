import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResearchWorkspace } from "./research-workspace";
import type { Document as WorkspaceDoc, RetrievedSource } from "@/types/api";

const mockDocument: WorkspaceDoc = {
  id: 42,
  user_id: 1,
  chat_id: 1,
  filename: "test_research.pdf",
  mime_type: "application/pdf",
  file_size: 2048,
  storage_url: "https://example.com/test_research.pdf",
  page_count: 3,
  status: "ready",
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

vi.mock("@/features/chat/components/chat-area", () => ({
  ChatArea: ({
    onCitationClick,
  }: {
    documentId?: number;
    onCitationClick?: (source: RetrievedSource) => void;
  }) => (
    <div data-testid="mocked-chat-area">
      <button
        type="button"
        data-testid="mock-same-doc-citation"
        onClick={() =>
          onCitationClick?.({
            id: 101,
            document_id: 42,
            page_number: 2,
            chunk_index: 0,
            distance: 0.1,
          })
        }
      >
        Same Doc Citation
      </button>
      <button
        type="button"
        data-testid="mock-cross-doc-citation"
        onClick={() =>
          onCitationClick?.({
            id: 102,
            document_id: 99,
            page_number: 7,
            chunk_index: 1,
            distance: 0.1,
          })
        }
      >
        Cross Doc Citation
      </button>
    </div>
  ),
}));

vi.mock("./document-pane", () => ({
  DocumentPane: ({
    navigationTarget,
  }: {
    document: WorkspaceDoc;
    navigationTarget?: { pageNumber: number; documentId: number } | null;
  }) => (
    <div data-testid="workspace-document-pane">
      <span data-testid="active-nav-page">
        {navigationTarget ? `Navigated Page ${navigationTarget.pageNumber}` : "No Nav Target"}
      </span>
    </div>
  ),
}));

describe("ResearchWorkspace Navigation & Layout", () => {
  it("renders active document awareness header with title and ready status", () => {
    render(<ResearchWorkspace document={mockDocument} />);

    expect(
      screen.getByTestId("research-workspace-document-title"),
    ).toHaveTextContent("test_research.pdf");
    expect(screen.getByTestId("status-badge-ready")).toBeInTheDocument();
  });

  it("handles same-document citation click by routing navigation target to document pane", () => {
    render(<ResearchWorkspace document={mockDocument} />);

    expect(screen.getByTestId("active-nav-page")).toHaveTextContent("No Nav Target");

    fireEvent.click(screen.getByTestId("mock-same-doc-citation"));

    expect(screen.getByTestId("active-nav-page")).toHaveTextContent("Navigated Page 2");
  });

  it("handles cross-document citation click by calling onDocumentNavigation", () => {
    const onDocumentNavigation = vi.fn();

    render(
      <ResearchWorkspace
        document={mockDocument}
        onDocumentNavigation={onDocumentNavigation}
      />,
    );

    fireEvent.click(screen.getByTestId("mock-cross-doc-citation"));

    expect(onDocumentNavigation).toHaveBeenCalledTimes(1);
    expect(onDocumentNavigation).toHaveBeenCalledWith(
      expect.objectContaining({
        documentId: 99,
        pageNumber: 7,
      }),
    );
  });
});
