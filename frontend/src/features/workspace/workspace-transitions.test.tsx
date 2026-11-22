import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState } from "react";
import { WorkspaceController } from "./components/workspace-controller";
import { WorkspaceSwitcher } from "./components/workspace-switcher";
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
let rerenderHarness: (() => void) | null = null;

function applyRouterUrl(url: string) {
  const queryPart = url.split("?")[1];
  mockSearchParams.clear();
  if (queryPart) {
    const params = new URLSearchParams(queryPart);
    params.forEach((value, key) => {
      mockSearchParams.set(key, value);
    });
  }
  if (rerenderHarness) {
    rerenderHarness();
  }
}

const mockRouterPush = vi.fn((url: string) => applyRouterUrl(url));
const mockRouterReplace = vi.fn((url: string) => applyRouterUrl(url));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush, replace: mockRouterReplace }),
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
    onDocumentNavigation,
  }: {
    document: Document;
    navigationTarget?: PdfNavigationTarget | null;
    onDocumentNavigation?: (target: PdfNavigationTarget) => void;
  }) => (
    <div data-testid="research-workspace-view">
      <span data-testid="active-doc-id">{document.id}</span>
      <span data-testid="navigation-target-state">
        {navigationTarget
          ? `doc:${navigationTarget.documentId}:page:${navigationTarget.pageNumber}:req:${navigationTarget.requestId}`
          : "none"}
      </span>
      {onDocumentNavigation && (
        <button
          type="button"
          data-testid="jump-same-doc-page-7"
          onClick={() =>
            onDocumentNavigation({
              documentId: document.id,
              pageNumber: 7,
              requestId: 777,
            })
          }
        >
          Jump Page 7
        </button>
      )}
    </div>
  ),
}));

vi.mock("./components/workspace-skeleton", () => ({
  WorkspaceSkeleton: () => <div data-testid="workspace-skeleton">Loading...</div>,
}));

// Stateful probes that verify actual React remount / local state reset on workspace transitions
vi.mock("./components/workspace-research-synthesis-panel", () => ({
  WorkspaceResearchSynthesisPanel: ({ workspaceId }: { workspaceId: number }) => {
    const [draftQuery, setDraftQuery] = useState("");
    return (
      <div data-testid="synthesis-panel">
        <span>{`Synthesis:${workspaceId}`}</span>
        <input
          aria-label="Synthesis draft query"
          value={draftQuery}
          onChange={(e) => setDraftQuery(e.target.value)}
        />
      </div>
    );
  },
}));

vi.mock("./components/workspace-document-manager", () => ({
  WorkspaceDocumentManager: ({ workspaceId }: { workspaceId: number }) => {
    const [selectedAttachIds, setSelectedAttachIds] = useState<number[]>([]);
    return (
      <div data-testid="document-manager">
        <span>{`Docs:${workspaceId}`}</span>
        <button
          type="button"
          data-testid="select-doc-to-attach"
          onClick={() => setSelectedAttachIds([901])}
        >
          Select 901
        </button>
        <span data-testid="pending-attach-count">{selectedAttachIds.length}</span>
      </div>
    );
  },
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
    rerenderHarness = null;
    useWorkspaceStore.getState().reset();
    useChatStore.getState().reset();
    useDocumentStore.getState().reset();
  });

  it("reconciles stale docId in URL and returns to clean chat when switching via WorkspaceSwitcher", async () => {
    const workspaces = [
      { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
      { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
    ];

    useWorkspaceStore.setState({
      workspaces,
      activeWorkspaceId: 1,
      documentsByWorkspace: {
        1: [makeWsDoc(12, 10)],
        2: [makeWsDoc(99, 20)],
      },
    });

    vi.spyOn(workspaceService, "listWorkspaces").mockResolvedValue(workspaces);
    vi.spyOn(workspaceService, "listDocuments").mockImplementation(async (wsId: number) =>
      wsId === 1 ? [makeWsDoc(12, 10)] : [makeWsDoc(99, 20)],
    );
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(documentApi, "get").mockImplementation(async (docId: number) => {
      if (docId === 12) return makeDoc(12, 10);
      if (docId === 99) return makeDoc(99, 20);
      throw new Error("Document not found");
    });

    // Preserve an unrelated query parameter alongside docId=12
    mockSearchParams.set("docId", "12");
    mockSearchParams.set("filter", "recent");

    const { rerender } = render(
      <>
        <WorkspaceSwitcher />
        <WorkspaceController />
      </>,
    );
    rerenderHarness = () =>
      rerender(
        <>
          <WorkspaceSwitcher />
          <WorkspaceController />
        </>,
      );

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("12");
    });

    // User clicks WorkspaceSwitcher dropdown and switches to Workspace B
    fireEvent.click(screen.getByRole("button", { name: /Workspace: Workspace A/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workspace B/i }));
    });

    // Stale docId=12 must be removed from URL while preserving unrelated query param `filter=recent`
    expect(mockSearchParams.get("docId")).toBeUndefined();
    expect(mockSearchParams.get("filter")).toBe("recent");
    expect(mockRouterReplace).toHaveBeenCalledWith("/dashboard?filter=recent");

    // Destination Workspace B renders clean chat view (never an error banner for Workspace A's doc)
    expect(screen.getByTestId("chat-area")).toBeDefined();
    expect(screen.queryByTestId("workspace-document-error")).toBeNull();
    expect(screen.queryByTestId("research-workspace-view")).toBeNull();
  });

  it("reconciles route when destination workspace cache is stale (cached [12] vs authoritative [99])", async () => {
    const workspaces = [
      { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
      { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
    ];

    // Workspace B's cached documentsByWorkspace[2] still holds stale [12] from before detachment
    useWorkspaceStore.setState({
      workspaces,
      activeWorkspaceId: 1,
      documentsByWorkspace: {
        1: [makeWsDoc(12, 10)],
        2: [makeWsDoc(12, 10)],
      },
    });

    vi.spyOn(workspaceService, "listWorkspaces").mockResolvedValue(workspaces);
    // Authoritative server response for Workspace B returns [99] (doc 12 was detached)
    vi.spyOn(workspaceService, "listDocuments").mockImplementation(async (wsId: number) =>
      wsId === 1 ? [makeWsDoc(12, 10)] : [makeWsDoc(99, 20)],
    );
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(documentApi, "get").mockImplementation(async (docId: number) => {
      if (docId === 12) return makeDoc(12, 10);
      return makeDoc(99, 20);
    });

    mockSearchParams.set("docId", "12");
    mockSearchParams.set("filter", "pinned");

    const { rerender } = render(
      <>
        <WorkspaceSwitcher />
        <WorkspaceController />
      </>,
    );
    rerenderHarness = () =>
      rerender(
        <>
          <WorkspaceSwitcher />
          <WorkspaceController />
        </>,
      );

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("12");
    });

    // Switch Workspace A -> B; initial optimistic check sees stale [12] in cache,
    // then authoritative listDocuments(2) returns [99] and forces route reconciliation.
    fireEvent.click(screen.getByRole("button", { name: /Workspace: Workspace A/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workspace B/i }));
    });

    await waitFor(() => {
      expect(mockSearchParams.get("docId")).toBeUndefined();
    });
    expect(mockSearchParams.get("filter")).toBe("pinned");
    expect(mockRouterReplace).toHaveBeenCalledWith("/dashboard?filter=pinned");
    expect(screen.getByTestId("chat-area")).toBeDefined();
    expect(screen.queryByTestId("research-workspace-view")).toBeNull();
    expect(screen.queryByTestId("workspace-document-error")).toBeNull();
  });

  it("never resurrects cleared citation target on A (doc 12, page 5) -> B -> A (doc 12) transition", async () => {
    const workspaces = [
      { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
      { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
    ];

    useWorkspaceStore.setState({
      workspaces,
      activeWorkspaceId: 1,
      documentsByWorkspace: {
        1: [makeWsDoc(12, 10)],
        2: [makeWsDoc(99, 20)],
      },
    });

    vi.spyOn(workspaceService, "listWorkspaces").mockResolvedValue(workspaces);
    vi.spyOn(workspaceService, "listDocuments").mockImplementation(async (wsId: number) =>
      wsId === 1 ? [makeWsDoc(12, 10)] : [makeWsDoc(99, 20)],
    );
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(documentApi, "get").mockImplementation(async (docId: number) => {
      if (docId === 12) return makeDoc(12, 10);
      return makeDoc(99, 20);
    });

    const { rerender } = render(
      <>
        <WorkspaceSwitcher />
        <WorkspaceController />
      </>,
    );
    rerenderHarness = () =>
      rerender(
        <>
          <WorkspaceSwitcher />
          <WorkspaceController />
        </>,
      );

    // 1. Click citation in Workspace A -> Doc 12 Page 5
    fireEvent.click(screen.getByTestId("cite-doc-12-page-5"));
    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("12");
    });
    expect(screen.getByTestId("navigation-target-state")).toHaveTextContent("doc:12:page:5:req:1");

    // 2. Verify same-document navigation updates to Page 7 with new requestId
    fireEvent.click(screen.getByTestId("jump-same-doc-page-7"));
    expect(screen.getByTestId("navigation-target-state")).toHaveTextContent("doc:12:page:7:req:777");

    // 3. Switch to Workspace B via WorkspaceSwitcher
    fireEvent.click(screen.getByRole("button", { name: /Workspace: Workspace A/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workspace B/i }));
    });
    expect(screen.getByTestId("chat-area")).toBeDefined();

    // 4. Switch back to Workspace A and reopen Doc 12 -> old citation target must NOT resurrect
    fireEvent.click(screen.getByRole("button", { name: /Workspace: Workspace B/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workspace A/i }));
    });

    mockSearchParams.set("docId", "12");
    rerenderHarness();

    await waitFor(() => {
      expect(screen.getByTestId("active-doc-id")).toHaveTextContent("12");
    });
    expect(screen.getByTestId("navigation-target-state")).toHaveTextContent("none");
  });

  it("keeps loading active when loadWorkspaces resolves before selectWorkspace and orders out-of-order list responses", async () => {
    let resolveList1!: (ws: { id: number; name: string; created_by: number; created_at: string; updated_at: string }[]) => void;
    let resolveList2!: (ws: { id: number; name: string; created_by: number; created_at: string; updated_at: string }[]) => void;
    let resolveDocsB!: (docs: WorkspaceDocument[]) => void;

    let callIndex = 0;
    vi.spyOn(workspaceService, "listWorkspaces").mockImplementation(() => {
      callIndex += 1;
      if (callIndex === 1) return new Promise((r) => { resolveList1 = r; });
      return new Promise((r) => { resolveList2 = r; });
    });
    vi.spyOn(workspaceService, "listDocuments").mockImplementation((wsId: number) => {
      if (wsId === 2) return new Promise((r) => { resolveDocsB = r; });
      return Promise.resolve([makeWsDoc(101, 1)]);
    });
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });

    const pList1 = workspaceActions.loadWorkspaces();
    const pList2 = workspaceActions.loadWorkspaces();
    const pSelectB = workspaceActions.selectWorkspace(2);

    // Resolve newer list2 first, then stale list1
    resolveList2([
      { id: 1, name: "Workspace A", created_by: 1, created_at: "", updated_at: "" },
      { id: 2, name: "Workspace B", created_by: 1, created_at: "", updated_at: "" },
    ]);
    await pList2;

    resolveList1([
      { id: 99, name: "Stale Workspace List", created_by: 1, created_at: "", updated_at: "" },
    ]);
    await pList1;

    // Stale list1 must NOT overwrite list2 or reset activeWorkspaceId=2, and isLoading stays true while selectWorkspace(2) is pending
    expect(useWorkspaceStore.getState().workspaces.map((w) => w.id)).toEqual([1, 2]);
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe(2);
    expect(useWorkspaceStore.getState().isLoading).toBe(true);

    // Complete selectWorkspace(2)
    resolveDocsB([makeWsDoc(202, 2)]);
    await pSelectB;

    expect(useWorkspaceStore.getState().isLoading).toBe(false);
    expect(useWorkspaceStore.getState().documentsByWorkspace[2]?.map((d) => d.document_id)).toEqual([202]);
  });

  it("resets local draft query and pending document selections across research workbench workspace switches", async () => {
    const workspaces = [
      { id: 42, name: "Alpha Lab", created_by: 1, created_at: "", updated_at: "" },
      { id: 99, name: "Beta Lab", created_by: 1, created_at: "", updated_at: "" },
    ];

    useWorkspaceStore.setState({ workspaces, activeWorkspaceId: 42 });
    vi.spyOn(workspaceService, "listWorkspaces").mockResolvedValue(workspaces);
    vi.spyOn(workspaceService, "listDocuments").mockResolvedValue([]);
    vi.spyOn(workspaceService, "listResearchRuns").mockResolvedValue({ items: [], total: 0 });

    mockSearchParams.set("view", "research");

    const { rerender } = render(
      <>
        <WorkspaceSwitcher />
        <WorkspaceController />
      </>,
    );
    rerenderHarness = () =>
      rerender(
        <>
          <WorkspaceSwitcher />
          <WorkspaceController />
        </>,
      );

    // Type draft query and select document to attach in Alpha Lab (42)
    const draftInput = screen.getByLabelText("Synthesis draft query") as HTMLInputElement;
    fireEvent.change(draftInput, { target: { value: "Compare transformer attention heads" } });
    expect(draftInput.value).toBe("Compare transformer attention heads");

    fireEvent.click(screen.getByTestId("select-doc-to-attach"));
    expect(screen.getByTestId("pending-attach-count")).toHaveTextContent("1");

    // Switch to Beta Lab (99) via WorkspaceSwitcher
    fireEvent.click(screen.getByRole("button", { name: /Workspace: Alpha Lab/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Beta Lab/i }));
    });

    // Both panels remount cleanly with empty draft query and zero stale attach selections
    expect(screen.getByTestId("synthesis-panel")).toHaveTextContent("Synthesis:99");
    expect((screen.getByLabelText("Synthesis draft query") as HTMLInputElement).value).toBe("");
    expect(screen.getByTestId("document-manager")).toHaveTextContent("Docs:99");
    expect(screen.getByTestId("pending-attach-count")).toHaveTextContent("0");
  });
});
