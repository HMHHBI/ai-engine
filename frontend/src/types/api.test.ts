import { describe, expect, it } from "vitest";
import type { RetrievedSource } from "@/types/api";

describe("RetrievedSource contract", () => {
  it("supports numeric document_id values", () => {
    const source: RetrievedSource = {
      id: 101,
      document_id: 42,
      page_number: 7,
      chunk_index: 3,
      distance: 0.123,
    };

    expect(source.document_id).toBe(42);
  });

  it("supports null document_id for legacy provenance", () => {
    const source: RetrievedSource = {
      id: 102,
      document_id: null,
      page_number: 4,
      chunk_index: 1,
      distance: 0.456,
    };

    expect(source.document_id).toBeNull();
  });
});
