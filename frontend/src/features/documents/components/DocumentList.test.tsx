import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import React from "react";
import { DocumentList } from "./DocumentList";
import type { Document } from "@/types/api";

const docs: Document[] = [
  {
    id: 1,
    user_id: 1,
    chat_id: 1,
    filename: "first.pdf",
    mime_type: "application/pdf",
    file_size: 100,
    page_count: 1,
    storage_url: null,
    status: "ready",
    error_message: null,
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:00Z",
  },
  {
    id: 2,
    user_id: 1,
    chat_id: 1,
    filename: "second.pdf",
    mime_type: "application/pdf",
    file_size: 200,
    page_count: 2,
    storage_url: null,
    status: "processing",
    error_message: null,
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:00Z",
  },
];

describe("DocumentList", () => {
  it("renders all documents preserving order", () => {
    render(<DocumentList documents={docs} selectedDocumentId={2} />);
    expect(screen.getByText("first.pdf")).toBeInTheDocument();
    expect(screen.getByText("second.pdf")).toBeInTheDocument();
    expect(screen.getByTestId("document-item-2")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("document-item-1")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});
