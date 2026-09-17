import { create } from "zustand";

export interface CitationTarget {
  documentId: number;
  pageNumber: number;
  sourceId: number;
}

interface WorkspaceStoreState {
  activeChatId: number | null;
  selectedDocumentId: number | null;
  viewerPage: number;
  viewerZoom: number;
  citationTarget: CitationTarget | null;

  setActiveChatId: (chatId: number | null) => void;
  setSelectedDocumentId: (documentId: number | null) => void;
  setViewerPage: (page: number) => void;
  setViewerZoom: (zoom: number) => void;
  setCitationTarget: (target: CitationTarget | null) => void;
  resetViewer: () => void;
  reset: () => void;
}

const DEFAULT_VIEWER_PAGE = 1;
const DEFAULT_VIEWER_ZOOM = 1;

export const useWorkspaceStore = create<WorkspaceStoreState>((set) => ({
  activeChatId: null,
  selectedDocumentId: null,
  viewerPage: DEFAULT_VIEWER_PAGE,
  viewerZoom: DEFAULT_VIEWER_ZOOM,
  citationTarget: null,

  setActiveChatId: (chatId) =>
    set({
      activeChatId: chatId,
    }),

  setSelectedDocumentId: (documentId) =>
    set({
      selectedDocumentId: documentId,
      viewerPage: DEFAULT_VIEWER_PAGE,
      citationTarget: null,
    }),

  setViewerPage: (page) =>
    set({
      viewerPage: Math.max(1, Math.floor(page)),
    }),

  setViewerZoom: (zoom) =>
    set({
      viewerZoom: Math.min(3, Math.max(0.5, zoom)),
    }),

  setCitationTarget: (target) =>
    set({
      citationTarget: target,
      ...(target
        ? {
            selectedDocumentId: target.documentId,
            viewerPage: Math.max(1, target.pageNumber),
          }
        : {}),
    }),

  resetViewer: () =>
    set({
      viewerPage: DEFAULT_VIEWER_PAGE,
      viewerZoom: DEFAULT_VIEWER_ZOOM,
      citationTarget: null,
    }),

  reset: () =>
    set({
      activeChatId: null,
      selectedDocumentId: null,
      viewerPage: DEFAULT_VIEWER_PAGE,
      viewerZoom: DEFAULT_VIEWER_ZOOM,
      citationTarget: null,
    }),
}));