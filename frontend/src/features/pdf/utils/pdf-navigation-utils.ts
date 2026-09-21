import type { RetrievedSource } from "@/types/api";
import type { PdfNavigationTarget } from "@/features/pdf/types/navigation";

export function createPdfNavigationTarget(
  source: RetrievedSource,
  activeDocumentId: number,
  requestId: number,
): PdfNavigationTarget | null {
  if (
    source.document_id === null ||
    source.document_id === undefined ||
    source.document_id !== activeDocumentId ||
    source.page_number === null
  ) {
    return null;
  }

  return {
    documentId: activeDocumentId,
    pageNumber: source.page_number,
    requestId,
  };
}
