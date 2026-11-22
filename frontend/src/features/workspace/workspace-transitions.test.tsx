import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceController } from "./components/workspace-controller";
import { workspaceActions } from "./actions/workspace-actions";
import { workspaceService } from "./services/workspace-service";
import { useWorkspaceStore } from "./store/workspace-store";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useDocumentStore } from "@/features/documents/document-store";
import { documentApi } from "@/lib/api/documents";
import type { Document, RetrievedSource } from "@/types/api";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";
import type { WorkspaceDocument } from "@/types/workspace";

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

vi.mock("./components/research-workspace", () => ({
  ResearchWorkspace: ({
    document,
    navigationTarget,
  }: {
    document: Document;
    navigationTarget?: PdfNavigationTarget | null;
  }) => (
    <div data-testid="research-workspace-view">
      <span data-testid="active-doc-id">{document.id}</span>
      <span data-testid="navigation-target-state">
        {navigationTarget
          ? `doc:${navigationTarget.documentId}:page:${navigationTarget.pageNumber}`
          : "none"}
      </span>
    </div>
  ),
}));

vi.mock("./components/workspace-skeleton", () => ({
  WorkspaceSkeleton: () => <div data-testid="workspace-skeleton">Loading...</div>,
}));

vi.mock("./components/workspace-research-synthesis-panel", () => ({
  WorkspaceResearchSynthesisPanel: ({ workspaceId }: { workspaceId: number }) => (
    <div data-testid="synthesis-panel">{`Synthesis:${workspaceId}`}</div>
  ),
}));

vi.mock("./components/workspace-document-manager", () => ({
  WorkspaceDocumentManager: ({ workspaceId }: { workspaceId: number }) => (
    <div data-testid="document-manager">{`Docs:${workspaceId}`}</div>
  ),
}));

vi.mock("@/features/chat/components/chat-area", () => ({
  ChatArea: ({
    onCitationClick,
  }: {
    onCitationClick?: (source: RetrievedSource) => void;
  }) => (
    <div data-testid="chat-area">
      {onCitationClick && (
        <button
          type="button"
          data-testid="cite-doc-12-page-5"
          onClick={() =>
            onCitationClick({
              id: 1,
              document_id: 12,
              page_number: 5,
              chunk_index: 0,
              distance: 0.1,
              snippet: "Evidence from workspace A",
            })
          }
        >
          Cite Doc 12
        </button>
      )}
    </div>
  ),
}));

function makeDoc(id: number, chatId = 1, status: Document["status"] = "ready"): Document {
  return {
    id,
    user_id: 1,
    chat_id: chatId,
    filename: `paper-${id}.pdf`,
    mime_type: "application/pdf",
    file_size: 2048,
    page_count: 8,
    storage_url: `https://example.com/paper-${id}.pdf`,
    status,
    error_message: null,
    created_at: "2026-11-22T00:00:00Z",
    updated_at: "2026-11-22T00:00:00Z",
  };
}

function makeWsDoc(documentId: number, chatId = 1): WorkspaceDocument {
  return {
    document_id: documentId,
    chat_id: chatId,
    filename: `paper-${documentId}.pdf`,
    mime_type: "application/pdf",
    status: "ready",
    added_by: 1,
    added_at: "2026-11-22T00:00:00Z",
  };
}

describe("Phase 2D: In-place workspace transition regressions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockSearchParams.clear();
    useWorkspaceStore.getState().reset();
    useChatStore.getState().reset();
    useDocumentStore.getState().reset();
  });

  it("switches in-place A -> B -> A and isolates workspace-scoped documents and research runs", async () => {
    useWorkspaceStore.setState({
      workspaces: [
        { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
        { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
      ],
      activeWorkspaceId: 1,
    });

    vi.spyOn(workspaceService, "listDocuments").mockImplementation(async (wsId: number) => {
      if (wsId === 1) return [makeWsDoc(101, 1)];
      if (wsId === 2) return [makeWsDoc(202, 2)];
      return [];
    });

    vi.spyOn(workspaceService, "listResearchRuns").mockImplementation(async (wsId: number) => ({
      items: [
        {
          id: wsId * 10,
          workspace_id: wsId,
          requester_id: 1,
          query: `Question for workspace ${wsId}`,
          status: "completed",
          answer: `Answer ${wsId}`,
          citations: [],
          run_metadata: {},
          created_at: "2026-11-22T00:00:00Z",
          completed_at: "2026-11-22T00:00:05Z",
          error_message: null,
        },
      ],
      total: 1,
    }));

    // Switch A -> B
    await workspaceActions.selectWorkspace(2);
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(2);
    expect(useWorkspaceStore.getState().documentsByWorkspace[2]?.map((d) => d.document_id)).toEqual([202]);
    expect(useWorkspaceStore.getState().researchRunsByWorkspace[2]?.[0]?.query).toBe("Question for workspace 2");

    // Switch B -> A
    await workspaceActions.selectWorkspace(1);
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(1);
    expect(useWorkspaceStore.getState().documentsByWorkspace[1]?.map((d) => d.document_id)).toEqual([101]);
    expect(useWorkspaceStore.getState().researchRunsByWorkspace[1]?.[0]?.query).toBe("Question for workspace 1");
  });

  it("prevents stale loading flags and late responses from overwriting state during rapid switching A -> B -> C", async () => {
    let resolveDocsA!: (docs: WorkspaceDocument[]) => void;
    let resolveDocsB!: (docs: WorkspaceDocument[]) => void;
    let resolveDocsC!: (docs: WorkspaceDocument[]) => void;

    vi.spyOn(workspaceService, "listDocuments").mockImplementation((wsId: number) => {
      if (wsId === 1) return new Promise((r) => { resolveDocsA = r; });
      if (wsId === 2) return new Promise((r) => { resolveDocsB = r; });
      return new Promise((r) => { resolveDocsC = r; });
    });
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });

    const pA = workspaceActions.selectWorkspace(1);
    const pB = workspaceActions.selectWorkspace(2);
    const pC = workspaceActions.selectWorkspace(3);

    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(3);
    expect(useWorkspaceStore.getState().isLoading).toBe(true);

    // Resolve C first, then late A and B
    resolveDocsC([makeWsDoc(303, 3)]);
    await pC;
    expect(useWorkspaceStore.getState().isLoading).toBe(false);
    expect(useWorkspaceStore.getState().documentsByWorkspace[3]?.map((d) => d.document_id)).toEqual([303]);

    resolveDocsA([makeWsDoc(101, 1)]);
    resolveDocsB([makeWsDoc(202, 2)]);
    await Promise.all([pA, pB]);

    // Active workspace remains 3 and loading remains false
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(3);
    expect(useWorkspaceStore.getState().isLoading).toBe(false);
  });

  it("blocks Workspace A document from leaking when switching to Workspace B and clears pending citation navigation", async () => {
    useWorkspaceStore.setState({
      workspaces: [
        { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
        { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
      ],
      activeWorkspaceId: 1,
      documentsByWorkspace: {
        1: [makeWsDoc(12, 10)],
        2: [makeWsDoc(99, 20)],
      },
    });

    vi.spyOn(documentApi, "get").mockImplementation(async (docId: number) => {
      if (docId === 12) return makeDoc(12, 10);
      if (docId === 99) return makeDoc(99, 20);
      throw new Error("Document not found");
    });

    const { rerender } = render(<WorkspaceController />);

    // 1. Click citation in Workspace A targeting Doc 12 Page 5
    fireEvent.click(screen.getByTestId("cite-doc-12-page-5"));
    expect(mockSearchParams.get("docId")).toBe("12");
    rerender(<WorkspaceController />);

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("12");
    });
    expect(screen.getByTestId("navigation-target-state")).toHaveTextContent("doc:12:page:5");

    // 2. Switch in-place to Workspace B where Doc 12 does NOT belong
    act(() => {
      useWorkspaceStore.getState().setActiveWorkspaceId(2);
    });
    rerender(<WorkspaceController />);

    // 3. Doc 12 must NOT leak into Workspace B; controller renders error alert instead
    await waitFor(() => {
      expect(screen.getByTestId("workspace-document-error")).toBeDefined();
    });
    expect(screen.queryByTestId("research-workspace-view")).toBeNull();

    // 4. Navigating to Workspace B's own Doc 99 must NOT carry over stale Page 5 target from Doc 12
    mockSearchParams.set("docId", "99");
    rerender(<WorkspaceController />);

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("99");
    });
    expect(screen.getByTestId("navigation-target-state")).toHaveTextContent("none");
  });

  it("prevents a late-resolving document fetch from Workspace A from overwriting Workspace B", async () => {
    useWorkspaceStore.setState({
      workspaces: [
        { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
        { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
      ],
      activeWorkspaceId: 1,
      documentsByWorkspace: {
        1: [makeWsDoc(55, 10)],
        2: [makeWsDoc(77, 20)],
      },
    });

    let resolveSlowDoc55!: (doc: Document) => void;
    vi.spyOn(documentApi, "get").mockImplementation((docId: number) => {
      if (docId === 55) {
        return new Promise<Document>((resolve) => {
          resolveSlowDoc55 = resolve;
        });
      }
      return Promise.resolve(makeDoc(77, 20));
    });

    mockSearchParams.set("docId", "55");
    const { rerender } = render(<WorkspaceController />);
    expect(screen.getByTestId("workspace-skeleton")).toBeDefined();

    // Before Doc 55 finishes loading, user switches to Workspace B and opens Doc 77
    act(() => {
      useWorkspaceStore.getState().setActiveWorkspaceId(2);
      mockSearchParams.set("docId", "77");
    });
    rerender(<WorkspaceController />);

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("77");
    });

    // Now the stale request for Doc 55 resolves late
    await act(async () => {
      resolveSlowDoc55(makeDoc(55, 10));
    });

    // Workspace B must still display Doc 77, untouched by late Doc 55 response
    expect(screen.getByTestId("active-doc-id")).toHaveTextContent("77");
  });

  it("remounts research synthesis workbench cleanly when switching workspaces in view=research", () => {
    useWorkspaceStore.setState({ activeWorkspaceId: 42 });
    mockSearchParams.set("view", "research");

    const { rerender } = render(<WorkspaceController />);
    expect(screen.getByTestId("synthesis-panel")).toHaveTextContent("Synthesis:42");
    expect(screen.getByTestId("document-manager")).toHaveTextContent("Docs:42");

    act(() => {
      useWorkspaceStore.getState().setActiveWorkspaceId(99);
    });
    rerender(<WorkspaceController />);

    expect(screen.getByTestId("synthesis-panel")).toHaveTextContent("Synthesis:99");
    expect(screen.getByTestId("document-manager")).toHaveTextContent("Docs:99");
  });
});
