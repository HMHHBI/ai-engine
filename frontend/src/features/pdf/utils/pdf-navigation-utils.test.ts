import { describe, expect, it } from "vitest";
import type { RetrievedSource } from "@/types/api";
import { createPdfNavigationTarget } from "@/features/pdf/utils/pdf-navigation-utils";

describe("PDF citation navigation", () => {
  it("P15: matching document navigates to the cited page", () => {
    const source: RetrievedSource = {
      id: 101,
      document_id: 42,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 1),
    ).toEqual({
      documentId: 42,
      pageNumber: 7,
      requestId: 1,
    });
  });

  it("P16: null document_id does not navigate", () => {
    const source: RetrievedSource = {
      id: 102,
      document_id: null,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 1),
    ).toBeNull();
  });

  it("P17: different document_id does not navigate", () => {
    const source: RetrievedSource = {
      id: 103,
      document_id: 99,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 1),
    ).toBeNull();
  });

  it("P18: null page_number does not navigate", () => {
    const source: RetrievedSource = {
      id: 104,
      document_id: 42,
      page_number: null,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 1),
    ).toBeNull();
  });
});
