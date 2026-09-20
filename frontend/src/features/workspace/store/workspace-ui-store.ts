import { create } from "zustand";
import { WORKSPACE_DOCUMENT_MIN_WIDTH } from "../constants/layout";
import type { WorkspaceUiState } from "../types";

export const useWorkspaceUiStore = create<WorkspaceUiState>((set) => ({
  panelWidth: WORKSPACE_DOCUMENT_MIN_WIDTH,
  isDocumentPaneCollapsed: false,

  setPanelWidth: (width: number) =>
    set({
      panelWidth: Math.max(WORKSPACE_DOCUMENT_MIN_WIDTH, width),
    }),

  setDocumentPaneCollapsed: (collapsed: boolean) =>
    set({
      isDocumentPaneCollapsed: collapsed,
    }),

  resetUiState: () =>
    set({
      panelWidth: WORKSPACE_DOCUMENT_MIN_WIDTH,
      isDocumentPaneCollapsed: false,
    }),
}));
