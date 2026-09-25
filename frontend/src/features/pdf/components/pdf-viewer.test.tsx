import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PdfViewer } from "./pdf-viewer";

vi.mock("@/features/pdf/hooks/use-pdf-document", () => ({
  usePdfDocument: (documentId: number | null) => {
    if (documentId === null) {
      return { status: "idle", objectUrl: null, error: null };
    }
    if (documentId === 999) {
      return {
        status: "error",
        objectUrl: null,
        error: { code: "NOT_FOUND", message: "Document not found" },
      };
    }
    return {
      status: "ready",
      objectUrl: "blob:http://localhost:3000/mock-pdf-blob",
      error: null,
    };
  },
}));

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
  Document: ({
    children,
    onLoadSuccess,
  }: {
    children: React.ReactNode;
    onLoadSuccess?: (pdf: { numPages: number }) => void;
  }) => {
    if (onLoadSuccess) {
      setTimeout(() => onLoadSuccess({ numPages: 10 }), 0);
    }
    return <div data-testid="mock-pdf-document">{children}</div>;
  },
}));

vi.mock("@/features/pdf/components/pdf-page", () => ({
  PdfPage: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid={`mock-pdf-page-${pageNumber}`}>Page {pageNumber}</div>
  ),
}));

describe("PdfViewer", () => {
  it("renders empty state when no document is selected", () => {
    render(<PdfViewer documentId={null} />);
    expect(screen.getByTestId("pdf-viewer-empty")).toBeInTheDocument();
  });

  it("renders error state when document fails to load", () => {
    render(<PdfViewer documentId={999} />);
    expect(screen.getByText("Document not found")).toBeInTheDocument();
  });

  it("navigates to page and applies visual focus on citation target", async () => {
    const { rerender } = render(
      <PdfViewer
        documentId={42}
        navigationTarget={null}
      />,
    );

    // Initial load settles with pages
    await screen.findByTestId("pdf-page-container");
    expect(screen.getByText("Page 1")).toBeInTheDocument();

    // Citation navigation target arrives
    rerender(
      <PdfViewer
        documentId={42}
        navigationTarget={{
          documentId: 42,
          pageNumber: 5,
          requestId: 1,
        }}
      />,
    );

    const pageContainer = await screen.findByTestId("pdf-page-container");
    expect(screen.getByText("Page 5")).toBeInTheDocument();

    // Verify visual focus ring
    expect(pageContainer).toHaveClass("ring-4");
    expect(pageContainer).toHaveClass("ring-primary/80");

    // Verify accessible screen-reader announcement
    expect(
      screen.getByTestId("pdf-navigation-announcement"),
    ).toHaveTextContent("Citation navigated to page 5.");
  });

  it("ignores navigation target meant for another document", async () => {
    const { rerender } = render(
      <PdfViewer
        documentId={42}
        navigationTarget={null}
      />,
    );

    await screen.findByTestId("pdf-page-container");
    expect(screen.getByText("Page 1")).toBeInTheDocument();

    // Navigation target meant for doc 99
    rerender(
      <PdfViewer
        documentId={42}
        navigationTarget={{
          documentId: 99,
          pageNumber: 8,
          requestId: 2,
        }}
      />,
    );

    // Page must remain on 1
    expect(screen.getByText("Page 1")).toBeInTheDocument();
  });
});
