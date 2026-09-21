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

  it("P19: matching citation after document switch targets the new document", () => {
    const source: RetrievedSource = {
      id: 105,
      document_id: 51,
      page_number: 8,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 51, 2),
    ).toEqual({
      documentId: 51,
      pageNumber: 8,
      requestId: 2,
    });

    expect(
      createPdfNavigationTarget(source, 42, 2),
    ).toBeNull();
  });

  it("rejects page zero", () => {
    const source: RetrievedSource = {
      id: 106,
      document_id: 42,
      page_number: 0,
      chunk_index: 1,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 3),
    ).toBeNull();
  });

  it("rejects negative page numbers", () => {
    const source: RetrievedSource = {
      id: 107,
      document_id: 42,
      page_number: -3,
      chunk_index: 1,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 4),
    ).toBeNull();
  });

  it("rejects non-integer page numbers", () => {
    const source: RetrievedSource = {
      id: 108,
      document_id: 42,
      page_number: 2.5,
      chunk_index: 1,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 42, 5),
    ).toBeNull();
  });
});
