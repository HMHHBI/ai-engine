import "@testing-library/jest-dom";

import {
  fireEvent,
  render,
  screen,
} from "@testing-library/react";

import {
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  DocumentListItem,
} from "./DocumentListItem";

import type { Document } from "@/types/api";

const baseDocument: Document = {
  id: 10,
  user_id: 1,
  chat_id: 20,
  filename: "research.pdf",
  mime_type: "application/pdf",
  file_size: 2048,
  page_count: 4,
  storage_url: null,
  status: "ready",
  error_message: null,
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
};

describe("DocumentListItem", () => {
  it("renders a ready document as selectable", () => {
    const onSelect = vi.fn();

    render(
      <DocumentListItem
        document={baseDocument}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(
      screen.getByTestId(
        "document-item-10",
      ),
    );

    expect(
      onSelect,
    ).toHaveBeenCalledWith(
      baseDocument,
    );

    expect(
      screen.getByTestId(
        "status-badge-ready",
      ),
    ).toBeInTheDocument();
  });

  it("renders extracting state and prevents selection", () => {
    const onSelect = vi.fn();

    render(
      <DocumentListItem
        document={{
          ...baseDocument,
          status: "extracting",
        }}
        onSelect={onSelect}
      />,
    );

    expect(
      screen.getByTestId(
        "status-badge-extracting",
      ),
    ).toHaveTextContent(
      "Extracting Text",
    );

    expect(
      screen.getByTestId(
        "document-lifecycle-10",
      ),
    ).toHaveTextContent(
      "Extracting Text",
    );

    fireEvent.click(
      screen.getByTestId(
        "document-item-10",
      ),
    );

    expect(
      onSelect,
    ).not.toHaveBeenCalled();
  });

  it("renders indexing state and prevents selection", () => {
    render(
      <DocumentListItem
        document={{
          ...baseDocument,
          status: "indexing",
        }}
      />,
    );

    expect(
      screen.getByTestId(
        "status-badge-indexing",
      ),
    ).toHaveTextContent(
      "Indexing Evidence",
    );
  });

  it("renders failed state with retry action", () => {
    const onRetry = vi.fn();

    render(
      <DocumentListItem
        document={{
          ...baseDocument,
          status: "failed",
          error_message:
            "Embedding failed.",
        }}
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByTestId(
        "status-badge-failed",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByTestId(
        "document-error-10",
      ),
    ).toHaveTextContent(
      "Embedding failed.",
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Retry document preparation",
        },
      ),
    );

    expect(
      onRetry,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 10,
        status: "failed",
      }),
    );
  });
});
