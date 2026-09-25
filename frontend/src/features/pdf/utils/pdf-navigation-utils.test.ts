import { describe, expect, it } from "vitest";
import type { RetrievedSource } from "@/types/api";
import { createPdfNavigationTarget } from "@/features/pdf/utils/pdf-navigation-utils";

describe("PDF citation navigation", () => {
  it("navigates to the cited page in the active document", () => {
    const source: RetrievedSource = {
      id: 101,
      document_id: 42,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 1),
    ).toEqual({
      documentId: 42,
      pageNumber: 7,
      requestId: 1,
    });
  });

  it("creates a target for a different document", () => {
    const source: RetrievedSource = {
      id: 103,
      document_id: 99,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 2),
    ).toEqual({
      documentId: 99,
      pageNumber: 7,
      requestId: 2,
    });
  });

  it("rejects a source without a document id", () => {
    const source: RetrievedSource = {
      id: 102,
      document_id: null,
      page_number: 7,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 1),
    ).toBeNull();
  });

  it("rejects a source without a page number", () => {
    const source: RetrievedSource = {
      id: 104,
      document_id: 42,
      page_number: null,
      chunk_index: 12,
      distance: 0.1,
    };

    expect(
      createPdfNavigationTarget(source, 1),
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
      createPdfNavigationTarget(source, 1),
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
      createPdfNavigationTarget(source, 1),
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
      createPdfNavigationTarget(source, 1),
    ).toBeNull();
  });
});
