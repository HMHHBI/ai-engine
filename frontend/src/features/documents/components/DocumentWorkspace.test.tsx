import "@testing-library/jest-dom";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { DocumentWorkspace } from "./DocumentWorkspace";
import { useDocumentStore } from "../document-store";
import { documentApi } from "@/lib/api/documents";

vi.mock("@/lib/api/documents", () => ({
  documentApi: {
    listForChat: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("DocumentWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentStore.getState().reset();
  });

  it("does not render when closed", () => {
    render(<DocumentWorkspace chatId={10} isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByTestId("document-workspace")).not.toBeInTheDocument();
  });

  it("renders empty state when chat has no documents", async () => {
    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([]);

    render(<DocumentWorkspace chatId={10} isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("document-empty-state")).toBeInTheDocument();
    });
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
  });

  it("renders document list when documents exist", async () => {
    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([
      {
        id: 1,
        user_id: 1,
        chat_id: 10,
        filename: "test.pdf",
        mime_type: "application/pdf",
        file_size: 100,
        page_count: 1,
        storage_url: null,
        status: "ready",
        error_message: null,
        created_at: "2026-09-06T00:00:00Z",
        updated_at: "2026-09-06T00:00:00Z",
      },
    ]);

    render(<DocumentWorkspace chatId={10} isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("test.pdf")).toBeInTheDocument();
    });
  });

  it("calls onClose when close button or backdrop is clicked", async () => {
    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([]);
    const onClose = vi.fn();
    render(<DocumentWorkspace chatId={10} isOpen={true} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByTestId("document-empty-state")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Close document workspace"));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("document-workspace-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("closes on Escape key press", async () => {
    vi.mocked(documentApi.listForChat).mockResolvedValueOnce([]);
    const onClose = vi.fn();
    render(<DocumentWorkspace chatId={10} isOpen={true} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByTestId("document-empty-state")).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
