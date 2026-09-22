export type WorkspaceMode = "standard" | "research";

export interface WorkspaceUiState {
  /** Width of the document pane in pixels */
  panelWidth: number;
  /** Whether the document pane is collapsed in desktop split view */
  isDocumentPaneCollapsed: boolean;

  /** Update transient panel width */
  setPanelWidth: (width: number) => void;
  /** Toggle or set document pane collapsed state */
  setDocumentPaneCollapsed: (collapsed: boolean) => void;
  /** Reset UI state to defaults */
  resetUiState: () => void;
}
