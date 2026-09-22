import type { RetrievedSource } from "@/types/api";

export const PDF_CITATION_FIXTURES = {
  matching: {
    id: 1,
    document_id: 42,
    page_number: 7,
    chunk_index: 12,
    distance: 0.1,
  },

  legacyDocumentIdNull: {
    id: 2,
    document_id: null,
    page_number: 7,
    chunk_index: 12,
    distance: 0.1,
  },

  wrongDocument: {
    id: 3,
    document_id: 99,
    page_number: 7,
    chunk_index: 12,
    distance: 0.1,
  },

  missingPage: {
    id: 4,
    document_id: 42,
    page_number: null,
    chunk_index: 12,
    distance: 0.1,
  },

  outOfBounds: {
    id: 5,
    document_id: 42,
    page_number: 999,
    chunk_index: 12,
    distance: 0.1,
  },
} satisfies Record<string, RetrievedSource>;
