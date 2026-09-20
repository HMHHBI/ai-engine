import { describe, it, expect, beforeEach } from "vitest";
import { useWorkspaceUiStore } from "./workspace-ui-store";
import { WORKSPACE_DOCUMENT_MIN_WIDTH } from "../constants/layout";

describe("WorkspaceUiStore (M4.1)", () => {
  beforeEach(() => {
    useWorkspaceUiStore.getState().resetUiState();
  });

  it("initializes with default panel width and uncollapsed state", () => {
    const state = useWorkspaceUiStore.getState();
    expect(state.panelWidth).toBe(WORKSPACE_DOCUMENT_MIN_WIDTH);
    expect(state.isDocumentPaneCollapsed).toBe(false);
  });

  it("updates panel width within valid bounds", () => {
    useWorkspaceUiStore.getState().setPanelWidth(520);
    expect(useWorkspaceUiStore.getState().panelWidth).toBe(520);
  });

  it("clamps panel width to at least WORKSPACE_DOCUMENT_MIN_WIDTH", () => {
    useWorkspaceUiStore.getState().setPanelWidth(200);
    expect(useWorkspaceUiStore.getState().panelWidth).toBe(WORKSPACE_DOCUMENT_MIN_WIDTH);
  });

  it("toggles document pane collapsed state", () => {
    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(true);
    expect(useWorkspaceUiStore.getState().isDocumentPaneCollapsed).toBe(true);

    useWorkspaceUiStore.getState().setDocumentPaneCollapsed(false);
    expect(useWorkspaceUiStore.getState().isDocumentPaneCollapsed).toBe(false);
  });

  it("does not track activeDocumentId inside Zustand (URL is canonical)", () => {
    const state = useWorkspaceUiStore.getState();
    expect((state as unknown as Record<string, unknown>).activeDocumentId).toBeUndefined();
  });
});
