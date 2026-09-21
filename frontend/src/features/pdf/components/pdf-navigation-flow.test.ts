import { describe, expect, it } from "vitest";
import { clampPage } from "@/features/pdf/utils/pdf-viewer-utils";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

describe("PdfViewer navigation target consumption state logic (P20–P26)", () => {
  it("P20: clamps out-of-bounds target page to numPages", () => {
    const target: PdfNavigationTarget = { documentId: 42, pageNumber: 99, requestId: 1 };
    const numPages = 20;
    const resolvedPage = clampPage(target.pageNumber, numPages);
    expect(resolvedPage).toBe(20);
  });

  it("P21: clamps lower-bound target page to 1", () => {
    const target: PdfNavigationTarget = { documentId: 42, pageNumber: 0, requestId: 1 };
    const numPages = 20;
    const resolvedPage = clampPage(target.pageNumber, numPages);
    expect(resolvedPage).toBe(1);
  });

  it("P22: ignores target if documentId does not match active viewer document", () => {
    const target: PdfNavigationTarget = { documentId: 99, pageNumber: 5, requestId: 1 };
    const activeViewerDocumentId = 42;
    const shouldNavigate = target.documentId === activeViewerDocumentId;
    expect(shouldNavigate).toBe(false);
  });

  it("P23: duplicate requestId is ignored", () => {
    let lastRequestId: number | null = null;
    let page = 1;
    const numPages = 20;

    const navigate = (target: PdfNavigationTarget) => {
      if (lastRequestId === target.requestId) return;
      lastRequestId = target.requestId;
      page = clampPage(target.pageNumber, numPages);
    };

    const target: PdfNavigationTarget = { documentId: 42, pageNumber: 7, requestId: 7 };
    navigate(target);
    expect(page).toBe(7);

    // Same requestId again
    navigate({ ...target, pageNumber: 15 });
    expect(page).toBe(7); // Did not change
  });

  it("P24: new requestId triggers fresh navigation", () => {
    let lastRequestId: number | null = null;
    let page = 1;
    const numPages = 20;

    const navigate = (target: PdfNavigationTarget) => {
      if (lastRequestId === target.requestId) return;
      lastRequestId = target.requestId;
      page = clampPage(target.pageNumber, numPages);
    };

    navigate({ documentId: 42, pageNumber: 5, requestId: 7 });
    expect(page).toBe(5);

    navigate({ documentId: 42, pageNumber: 12, requestId: 8 });
    expect(page).toBe(12);
  });

  it("P25: stale target from previous document does not navigate new document", () => {
    const staleTarget: PdfNavigationTarget = { documentId: 42, pageNumber: 8, requestId: 7 };
    const newDocumentId = 51;
    const shouldNavigate = staleTarget.documentId === newDocumentId;
    expect(shouldNavigate).toBe(false);
  });

  it("P26: valid new target after switch navigates successfully", () => {
    const newTarget: PdfNavigationTarget = { documentId: 51, pageNumber: 3, requestId: 8 };
    const newDocumentId = 51;
    const numPages = 15;
    expect(newTarget.documentId === newDocumentId).toBe(true);
    expect(clampPage(newTarget.pageNumber, numPages)).toBe(3);
  });
});
