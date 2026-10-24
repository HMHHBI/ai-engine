import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceController } from "./workspace-controller";
import { useWorkspaceStore } from "../store/workspace-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";
import { documentApi } from "@/lib/api/documents";
import type { RetrievedSource, Document } from "@/types/api";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

const mockSearchParams = new Map<string, string>();
const mockRouterPush = vi.fn((url: string) => {
  const queryPart = url.split("?")[1];
  mockSearchParams.clear();
  if (queryPart) {
    const params = new URLSearchParams(queryPart);
    params.forEach((value, key) => {
      mockSearchParams.set(key, value);
    });
  }
});

const createMockDocument = (id: number, chatId = 1): Document => ({
  id,
  user_id: 1,
  chat_id: chatId,
  filename: `doc-${id}.pdf`,
  status: "ready",
  page_count: 20,
  mime_type: "application/pdf",
  file_size: 10240,
  storage_url: `https://example.com/doc-${id}.pdf`,
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

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
    navigationTarget,
    onDocumentNavigation,
  }: {
    document: Document;
    navigationTarget?: PdfNavigationTarget | null;
    onDocumentNavigation?: (target: PdfNavigationTarget) => void;
  }) => (
    <div data-testid="research-workspace-mock">
      <span data-testid="active-doc-indicator">Research Workspace for Doc {document.id}</span>
      {navigationTarget && (
        <span data-testid="viewer-navigation-target">
          Navigated to Doc {navigationTarget.documentId} Page {navigationTarget.pageNumber}
        </span>
      )}
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

vi.mock("./workspace-skeleton", () => ({
  WorkspaceSkeleton: () => <div data-testid="workspace-skeleton-mock">Loading Workspace...</div>,
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
    useWorkspaceStore.getState().reset();
    useChatStore.setState({ activeChatId: 1 });
    useDocumentStore.setState({ documentsByChat: {} });
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

  it("exercises real resolver hook: resolves uncached Document B via documentApi.get() fallback, shows skeleton, and navigates viewer to page 3", async () => {
    // 1. Initial State: Chat session 1 has only Document 12 in memory
    const doc12 = createMockDocument(12, 1);
    const doc88 = createMockDocument(88, 1);

    useDocumentStore.getState().setDocuments(1, [doc12]);
    mockSearchParams.set("docId", "12");

    // Deferred promise to explicitly control when documentApi.get resolves
    let resolveDoc88Fetch!: (doc: Document) => void;
    const pendingFetchPromise = new Promise<Document>((resolve) => {
      resolveDoc88Fetch = resolve;
    });

    const getSpy = vi
      .spyOn(documentApi, "get")
      .mockImplementation((id: number) => {
        if (id === 88) return pendingFetchPromise;
        return Promise.resolve(createMockDocument(id, 1));
      });

    const { rerender } = render(<WorkspaceController />);
    expect(screen.getByText("Research Workspace for Doc 12")).toBeDefined();

    // 2. User clicks citation targeting uncached Document 88 (Page 3)
    const switchBtn = screen.getByTestId("cross-doc-nav-btn");
    act(() => {
      fireEvent.click(switchBtn);
    });

    expect(mockRouterPush).toHaveBeenCalledWith("/dashboard?docId=88");

    // 3. Next.js router reflects updated query param docId=88
    mockSearchParams.set("docId", "88");
    rerender(<WorkspaceController />);

    // 4. Verify real hook initiated API fetch for doc 88 and Controller renders WorkspaceSkeleton
    expect(getSpy).toHaveBeenCalledWith(88, expect.any(Object));
    expect(screen.getByTestId("workspace-skeleton-mock")).toBeDefined();
    expect(screen.queryByTestId("research-workspace-mock")).toBeNull();

    // 5. Complete asynchronous API fetch for Document 88
    await act(async () => {
      resolveDoc88Fetch(doc88);
    });

    // 6. Verify Workspace mounts Document 88 and viewer receives navigation target
    await waitFor(() => {
      expect(screen.getByText("Research Workspace for Doc 88")).toBeDefined();
    });

    const targetElement = screen.getByTestId("viewer-navigation-target");
    expect(targetElement).toBeDefined();
    expect(targetElement).toHaveTextContent("Navigated to Doc 88 Page 3");
  });

  it("displays visible error banner when candidate document fails to resolve (not_found) and dismisses cleanly", async () => {
    mockSearchParams.set("docId", "999");
    vi.spyOn(documentApi, "get").mockRejectedValue(new Error("Document not found"));

    render(<WorkspaceController />);

    const errorBanner = await screen.findByTestId("workspace-document-error");
    expect(errorBanner).toBeDefined();
    expect(errorBanner).toHaveTextContent("Unable to load document #999.");

    // Dismiss button returns to clean chat
    const dismissBtn = screen.getByText("Dismiss & Return to Chat");
    fireEvent.click(dismissBtn);

    expect(mockRouterPush).toHaveBeenCalledWith("/dashboard");
  });

  it("displays visible error banner when candidate document is in error state", async () => {
    mockSearchParams.set("docId", "555");
    vi.spyOn(documentApi, "get").mockRejectedValue(new Error("Network failure"));

    render(<WorkspaceController />);

    const errorBanner = await screen.findByTestId("workspace-document-error");
    expect(errorBanner).toBeDefined();
    expect(errorBanner).toHaveTextContent("Unable to load document #555.");
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
