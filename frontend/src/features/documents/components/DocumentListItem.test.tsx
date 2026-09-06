import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import React from "react";
import { DocumentListItem } from "./DocumentListItem";
import type { Document } from "@/types/api";

const mockDoc: Document = {
  id: 1,
  user_id: 10,
  chat_id: 5,
  filename: "research_paper.pdf",
  mime_type: "application/pdf",
  file_size: 1024 * 1024 * 2.5,
  page_count: 14,
  storage_url: null,
  status: "ready",
  error_message: null,
  created_at: "2026-09-06T00:00:00Z",
  updated_at: "2026-09-06T00:00:00Z",
};

describe("DocumentListItem", () => {
  it("renders filename and metadata correctly", () => {
    render(<DocumentListItem document={mockDoc} />);
    expect(screen.getByText("research_paper.pdf")).toBeInTheDocument();
    expect(screen.getByText("PDF · 14 pages · 2.5 MB")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge-ready")).toBeInTheDocument();
  });

  it("handles selection clicks", () => {
    const onSelect = vi.fn();
    render(<DocumentListItem document={mockDoc} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("document-item-1"));
    expect(onSelect).toHaveBeenCalledWith(mockDoc);
  });

  it("handles keyboard enter selection", () => {
    const onSelect = vi.fn();
    render(<DocumentListItem document={mockDoc} onSelect={onSelect} />);
    const item = screen.getByTestId("document-item-1");
    fireEvent.keyDown(item, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(mockDoc);
  });
});
