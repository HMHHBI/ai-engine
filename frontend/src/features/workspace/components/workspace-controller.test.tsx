import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceController } from "./workspace-controller";
import { useWorkspaceStore } from "../store/workspace-store";
import type { RetrievedSource, Document } from "@/types/api";

const mockSearchParams = new Map<string, string>();
const mockRouterPush = vi.fn();

let mockResolutionState: {
  status: "idle" | "loading" | "resolved" | "not_found" | "error";
  document: Document | null;
  error: string | null;
} = { status: "idle", document: null, error: null };

vi.mock("../hooks/use-resolved-workspace-document", () => ({
  useResolvedWorkspaceDocument: () => mockResolutionState,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/dashboard",
  useSearchParams: () => ({
    get: (key: string) => mockSearchParams.get(key) ?? null,
    toString: () => {
      const entries = Array.from(mockSearchParams.entries());
      return entries.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
    },
  }),
}));

vi.mock("./research-workspace", () => ({
  ResearchWorkspace: ({
    document,
    onDocumentNavigation,
  }: {
    document: Document;
    onDocumentNavigation?: (target: unknown) => void;
  }) => (
    <div data-testid="research-workspace-mock">
      <span>Research Workspace for Doc {document.id}</span>
      {onDocumentNavigation && (
        <button
          data-testid="cross-doc-nav-btn"
          type="button"
          onClick={() =>
            onDocumentNavigation({
              documentId: 88,
              pageNumber: 3,
              requestId: 99,
            })
          }
        >
          Switch to Doc 88
        </button>
      )}
    </div>
  ),
}));

vi.mock("./workspace-research-synthesis-panel", () => ({
  WorkspaceResearchSynthesisPanel: ({ workspaceId }: { workspaceId: number }) => (
    <div data-testid="synthesis-panel-mock">Synthesis Panel {workspaceId}</div>
  ),
}));

vi.mock("./workspace-document-manager", () => ({
  WorkspaceDocumentManager: ({ workspaceId }: { workspaceId: number }) => (
    <div data-testid="doc-manager-mock">Doc Manager {workspaceId}</div>
  ),
}));

vi.mock("@/features/chat/components/chat-area", () => ({
  ChatArea: ({
    onCitationClick,
  }: {
    onCitationClick?: (source: RetrievedSource) => void;
  }) => (
    <div data-testid="chat-area-mock">
      Chat Area
      {onCitationClick && (
        <button
          data-testid="trigger-citation-click"
          type="button"
          onClick={() =>
            onCitationClick({
              id: 101,
              document_id: 12,
              page_number: 5,
              chunk_index: 2,
              distance: 0.15,
              snippet: "Test snippet content",
            })
          }
        >
          Click Citation
        </button>
      )}
    </div>
  ),
}));

describe("WorkspaceController Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams.clear();
    mockResolutionState = { status: "idle", document: null, error: null };
    useWorkspaceStore.getState().reset();
  });

  it("renders ChatArea by default", () => {
    render(<WorkspaceController />);
    expect(screen.getByTestId("chat-area-mock")).toBeDefined();
  });

  it("navigates to document viewer when citation is clicked in default chat view", () => {
    render(<WorkspaceController />);
    const citationBtn = screen.getByTestId("trigger-citation-click");
    expect(citationBtn).toBeDefined();

    fireEvent.click(citationBtn);

    expect(mockRouterPush).toHaveBeenCalledTimes(1);
    expect(mockRouterPush).toHaveBeenCalledWith("/dashboard?docId=12");
  });

  it("handles cross-document switching from active document viewer", () => {
    mockSearchParams.set("docId", "12");
    mockResolutionState = {
      status: "resolved",
      document: {
        id: 12,
        chat_id: 1,
        filename: "doc-a.pdf",
        status: "ready",
        page_count: 5,
        created_at: "2026-01-01T00:00:00Z",
      },
      error: null,
    };

    render(<WorkspaceController />);
    expect(screen.getByText("Research Workspace for Doc 12")).toBeDefined();

    // Trigger cross-doc switch to Document 88
    const switchBtn = screen.getByTestId("cross-doc-nav-btn");
    fireEvent.click(switchBtn);

    expect(mockRouterPush).toHaveBeenCalledWith("/dashboard?docId=88");
  });

  it("displays visible error banner when candidate document fails to resolve and dismisses cleanly", () => {
    mockSearchParams.set("docId", "999");
    mockResolutionState = {
      status: "not_found",
      document: null,
      error: "Document not found in the active research session.",
    };

    render(<WorkspaceController />);

    const errorBanner = screen.getByTestId("workspace-document-error");
    expect(errorBanner).toBeDefined();
    expect(errorBanner).toHaveTextContent("Unable to load document #999.");

    // Dismiss button returns to clean chat
    const dismissBtn = screen.getByText("Dismiss & Return to Chat");
    fireEvent.click(dismissBtn);

    expect(mockRouterPush).toHaveBeenCalledWith("/dashboard");
  });

  it("mounts and renders synthesis workbench when view=research is active", () => {
    mockSearchParams.set("view", "research");
    useWorkspaceStore.setState({ activeWorkspaceId: 42 });

    render(<WorkspaceController />);

    expect(screen.getByTestId("workspace-synthesis-view")).toBeDefined();
    expect(screen.getByTestId("synthesis-panel-mock")).toBeDefined();
    expect(screen.getByTestId("doc-manager-mock")).toBeDefined();
    expect(screen.getByText("Synthesis Panel 42")).toBeDefined();
  });

  it("renders empty state notice when view=research has no active workspace", () => {
    mockSearchParams.set("view", "research");
    useWorkspaceStore.setState({ activeWorkspaceId: null });

    render(<WorkspaceController />);

    expect(screen.getByTestId("workspace-synthesis-empty")).toBeDefined();
    expect(screen.getByText(/No Workspace Selected/i)).toBeDefined();
  });
});
