import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceDocumentManager } from "./workspace-document-manager";
import { useWorkspaceStore } from "../store/workspace-store";
import { workspaceActions } from "../actions/workspace-actions";
import { apiClient } from "@/lib/api/client";

vi.mock("../actions/workspace-actions", () => ({
  workspaceActions: {
    loadDocuments: vi.fn(),
    attachDocuments: vi.fn(),
    detachDocument: vi.fn(),
  },
}));

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("WorkspaceDocumentManager", () => {
  const mockAttached = [
    { document_id: 101, filename: "PaperA.pdf", chat_id: null, mime_type: "pdf", status: "ready", added_by: 1, added_at: "" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.getState().reset();
  });

  it("loads documents on mount and displays attached documents", () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 5: mockAttached },
    });
    vi.mocked(apiClient.get).mockResolvedValueOnce([]);

    render(<WorkspaceDocumentManager workspaceId={5} />);

    expect(workspaceActions.loadDocuments).toHaveBeenCalledWith(5);
    expect(screen.getByText("PaperA.pdf")).toBeDefined();
    expect(screen.getByText("1 attached")).toBeDefined();
  });

  it("attaches unattached documents when selected", async () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 5: mockAttached },
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce([
      { id: 101, filename: "PaperA.pdf", user_id: 1, status: "ready", content_hash: "h1", created_at: "", updated_at: "" },
      { id: 102, filename: "PaperB.pdf", user_id: 1, status: "ready", content_hash: "h2", created_at: "", updated_at: "" },
    ]);

    render(<WorkspaceDocumentManager workspaceId={5} />);

    const unattachedCheckbox = await screen.findByLabelText(/PaperB.pdf/i);
    fireEvent.click(unattachedCheckbox);

    const attachBtn = screen.getByRole("button", { name: /Attach Selected \(1\)/i });
    fireEvent.click(attachBtn);

    expect(workspaceActions.attachDocuments).toHaveBeenCalledWith(5, [102]);
  });

  it("detaches document on delete button click", () => {
    useWorkspaceStore.setState({
      documentsByWorkspace: { 5: mockAttached },
    });
    vi.mocked(apiClient.get).mockResolvedValueOnce([]);

    render(<WorkspaceDocumentManager workspaceId={5} />);

    const detachBtn = screen.getByRole("button", { name: /Detach PaperA.pdf/i });
    fireEvent.click(detachBtn);

    expect(workspaceActions.detachDocument).toHaveBeenCalledWith(5, 101);
  });
});

  it("resets selectedToAttach when workspaceId changes without unmounting", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([
      { id: 201, filename: "PaperX.pdf", user_id: 1, status: "ready", content_hash: "hx", created_at: "", updated_at: "" },
    ]);

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
