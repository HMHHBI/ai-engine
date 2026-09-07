import React from "react";
import type { Document } from "@/types/api";
import { DocumentListItem } from "./DocumentListItem";

interface DocumentListProps {
  documents: Document[];
  selectedDocumentId?: number | null;
  onSelectDocument?: (document: Document) => void;
  onEditDocument?: (document: Document) => void;
  onDeleteDocument?: (document: Document) => void;
}

export function DocumentList({
  documents,
  selectedDocumentId,
  onSelectDocument,
  onEditDocument,
  onDeleteDocument,
}: DocumentListProps) {
  return (
    <div className="space-y-2" data-testid="document-list">
      {documents.map((doc) => (
        <DocumentListItem
          key={doc.id}
          document={doc}
          isSelected={selectedDocumentId === doc.id}
          onSelect={onSelectDocument}
          onEdit={onEditDocument}
          onDelete={onDeleteDocument}
        />
      ))}
    </div>
  );
}
