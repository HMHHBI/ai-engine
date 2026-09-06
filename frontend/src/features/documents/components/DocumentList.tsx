import React from "react";
import type { Document } from "@/types/api";
import { DocumentListItem } from "./DocumentListItem";

interface DocumentListProps {
  documents: Document[];
  selectedDocumentId?: number | null;
  onSelectDocument?: (document: Document) => void;
}

export function DocumentList({
  documents,
  selectedDocumentId,
  onSelectDocument,
}: DocumentListProps) {
  return (
    <div className="space-y-2" data-testid="document-list">
      {documents.map((doc) => (
        <DocumentListItem
          key={doc.id}
          document={doc}
          isSelected={selectedDocumentId === doc.id}
          onSelect={onSelectDocument}
        />
      ))}
    </div>
  );
}
