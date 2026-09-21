import type { PDFPageProxy } from "pdfjs-dist";
import type { PdfNavigationTarget } from "./navigation";

export type PdfDocumentStatus =
  | "idle"
  | "loading"
  | "loaded"
  | "error";

export type PdfDocumentErrorCode =
  | "NOT_FOUND"
  | "UNAUTHORIZED"
  | "INVALID_PDF"
  | "NETWORK_ERROR"
  | "SERVER_ERROR"
  | "UNKNOWN";

export interface PdfDocumentError {
  code: PdfDocumentErrorCode;
  message: string;
  status?: number;
}

export interface PdfDocumentState {
  status: PdfDocumentStatus;
  blob: Blob | null;
  objectUrl: string | null;
  error: PdfDocumentError | null;
}

export interface PdfPageProps {
  pageNumber: number;
  scale: number;
  width?: number;
  onRenderSuccess?: () => void;
  onRenderError?: (error: Error) => void;
  onLoadSuccess?: (page: PDFPageProxy) => void;
}

export interface PdfToolbarProps {
  currentPage: number;
  numPages: number;
  scale: number;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onResetZoom: () => void;
  onFitWidth: () => void;
  onFitHeight: () => void;
}

export interface PdfViewerProps {
  documentId: number | null;
  navigationTarget?: PdfNavigationTarget | null;
}
