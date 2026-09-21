import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentPane } from "@/features/workspace/components/document-pane";

vi.mock("@/features/pdf/components/pdf-viewer", () => ({
  PdfViewer: ({
    documentId,
  }: {
    documentId: number | null;
  }) => (
    <div data-testid="mock-pdf-viewer">
      PDF viewer: {documentId}
    </div>
  ),
}));

const documentFixture = {
  id: 42,
  user_id: 10,
  chat_id: 5,
  filename: "research-paper.pdf",
  mime_type: "application/pdf",
  file_size: 2048,
  page_count: 12,
  storage_url: null,
  status: "ready" as const,
  error_message: null,
  created_at: "2026-09-21T00:00:00Z",
  updated_at: "2026-09-21T00:00:00Z",
};

describe("DocumentPane", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("preserves the existing document pane boundary", () => {
    render(<DocumentPane document={documentFixture} />);

    expect(
      screen.getByTestId("workspace-document-pane"),
    ).toBeInTheDocument();

    expect(
      screen.getByTestId("pdf-viewer-boundary"),
    ).toBeInTheDocument();
  });

  it("renders the document filename", () => {
    render(<DocumentPane document={documentFixture} />);

    expect(
      screen.getByTestId("workspace-document-title"),
    ).toHaveTextContent("research-paper.pdf");
  });

  it("passes the server document id to PdfViewer", async () => {
    render(<DocumentPane document={documentFixture} />);

    expect(
      await screen.findByTestId("mock-pdf-viewer"),
    ).toHaveTextContent("PDF viewer: 42");
  });

  it("preserves the close button contract", () => {
    const onClose = vi.fn();

    render(<DocumentPane document={documentFixture} onClose={onClose} />);

    const button = screen.getByTestId("workspace-close-button");
    expect(button).toBeInTheDocument();
  });

  it("does not render a close button when onClose is omitted", () => {
    render(<DocumentPane document={documentFixture} />);

    expect(
      screen.queryByTestId("workspace-close-button"),
    ).not.toBeInTheDocument();
  });
});
