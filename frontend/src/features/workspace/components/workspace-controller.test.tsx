import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceController } from "./workspace-controller";
import { useWorkspaceStore } from "../store/workspace-store";
import type { RetrievedSource } from "@/types/api";

const mockSearchParams = new Map<string, string>();
const mockRouterPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/dashboard",
  useSearchParams: () => ({
    get: (key: string) => mockSearchParams.get(key) ?? null,
    toString: () => "",
  }),
}));

vi.mock("./research-workspace", () => ({
  ResearchWorkspace: () => <div data-testid="research-workspace-mock">Research Workspace</div>,
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
