import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceDocumentManager } from "./workspace-document-manager";
import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { apiClient } from "@/lib/api/client";
import type { Document as ApiDocument } from "@/types/api";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

vi.mock("../actions/workspace-actions", () => ({
  workspaceActions: {
    loadDocuments: vi.fn(),
    attachDocuments: vi.fn(),
    detachDocument: vi.fn(),
  },
}));

function createMockApiDoc(overrides: Partial<ApiDocument> = {}): ApiDocument {
  return {
    id: 1,
    filename: "Doc.pdf",
    chat_id: 1,
    mime_type: "application/pdf",
    file_size: 1024,
    page_count: 5,
    status: "ready",
    user_id: 1,
    storage_url: null,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
    error_message: null,
    ...overrides,
  };
}

describe("WorkspaceDocumentManager", () => {
  const mockWorkspaceId = 1;
  const mockAttachedDocs = [
    {
      document_id: 1,
      filename: "Report.pdf",
      chat_id: 1,
      mime_type: "application/pdf",
      status: "ready",
      added_by: 1,
      added_at: "2026-03-01T00:00:00Z",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.getState().reset();
    useWorkspaceStore.setState({
      documentsByWorkspace: {
        [mockWorkspaceId]: mockAttachedDocs,
      },
    });
  });

  it("loads documents on mount and displays attached documents", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce([]);

    render(<WorkspaceDocumentManager workspaceId={mockWorkspaceId} />);

    expect(workspaceActions.loadDocuments).toHaveBeenCalledWith(mockWorkspaceId);
    expect(screen.getByText("Report.pdf")).toBeDefined();
    expect(screen.getByText("1 attached")).toBeDefined();
  });

  it("attaches unattached documents when selected", async () => {
    const unattachedDocs = [
      createMockApiDoc({ id: 2, filename: "Paper.pdf" }),
    ];

    vi.mocked(apiClient.get).mockResolvedValueOnce(unattachedDocs);

    render(<WorkspaceDocumentManager workspaceId={mockWorkspaceId} />);

    const checkbox = await screen.findByLabelText(/Paper.pdf/i);
    fireEvent.click(checkbox);

    const attachButton = screen.getByRole("button", { name: /Attach Selected \(1\)/i });
    fireEvent.click(attachButton);

    expect(workspaceActions.attachDocuments).toHaveBeenCalledWith(mockWorkspaceId, [2]);
  });

  it("detaches document on delete button click", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce([]);

    render(<WorkspaceDocumentManager workspaceId={mockWorkspaceId} />);

    const deleteBtn = screen.getByRole("button", { name: /Detach Report.pdf/i });
    fireEvent.click(deleteBtn);

    expect(workspaceActions.detachDocument).toHaveBeenCalledWith(mockWorkspaceId, 1);
  });

  it("resets selectedToAttach when workspaceId changes without unmounting", async () => {
    const availableDocs = [
      createMockApiDoc({ id: 201, filename: "PaperX.pdf" }),
    ];
    vi.mocked(apiClient.get).mockResolvedValue(availableDocs);

    useWorkspaceStore.setState({
      documentsByWorkspace: { 1: [], 2: [] },
    });

    const { rerender } = render(<WorkspaceDocumentManager workspaceId={1} />);

    const checkbox = await screen.findByLabelText(/PaperX.pdf/i);
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("button", { name: /Attach Selected \(1\)/i })).toBeDefined();

    // Switch workspace to 2 without unmounting
    rerender(<WorkspaceDocumentManager workspaceId={2} />);

    // Selection must be cleared
    const checkboxAfterSwitch = (await screen.findByLabelText(/PaperX.pdf/i)) as HTMLInputElement;
    expect(checkboxAfterSwitch.checked).toBe(false);
  });

  it("restarts loading state and shows indicator when switching workspaces", async () => {
    let resolveSecondCall: (value: ApiDocument[]) => void = () => {};
    const secondCallPromise = new Promise<ApiDocument[]>((resolve) => {
      resolveSecondCall = resolve;
    });

    const firstBatch = [
      createMockApiDoc({ id: 1, filename: "Paper1.pdf" }),
    ];

    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(firstBatch)
      .mockReturnValueOnce(secondCallPromise);

    useWorkspaceStore.setState({
      documentsByWorkspace: { 1: [], 2: [] },
    });

    const { rerender } = render(<WorkspaceDocumentManager workspaceId={1} />);

    expect(await screen.findByText("Paper1.pdf")).toBeDefined();
    expect(screen.queryByTestId("fetching-docs-indicator")).toBeNull();

    // Switch workspace to 2 without unmounting
    rerender(<WorkspaceDocumentManager workspaceId={2} />);

    // Loading indicator must be immediately visible again
    expect(screen.getByTestId("fetching-docs-indicator")).toBeDefined();
    expect(screen.getByText("Loading documents...")).toBeDefined();

    await act(async () => {
      resolveSecondCall([
        createMockApiDoc({ id: 2, filename: "Paper2.pdf" }),
      ]);
    });

    expect(await screen.findByText("Paper2.pdf")).toBeDefined();
    expect(screen.queryByTestId("fetching-docs-indicator")).toBeNull();
  });
});
