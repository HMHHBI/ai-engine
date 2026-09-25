import type {
  AIModel,
  AIProvider,
  ChatMessage,
  ChatSession,
  Document,
  RetrievedSource,
} from "@/types/api";

export type ResearchMode = "academic" | "legal" | "general" | "simple";

export type DocumentPreparationStage =
  | "uploading"
  | "extracting"
  | "indexing"
  | "ready"
  | "failed";

export interface DocumentPreparationState {
  stage: DocumentPreparationStage;
  progress: number | null;
  errorMessage: string | null;
  retryable: boolean;
  updatedAt: string | null;
}

export interface ResearchDocument extends Document {
  preparation?: DocumentPreparationState;
}

export interface ResearchEvidence {
  id: string;
  source: RetrievedSource;
  documentId: number | null;
  documentTitle: string;
  pageNumber: number | null;
  quote: string | null;
  technicalDetails?: {
    chunkIndex: number | null;
    distance: number;
  };
}

export function toResearchEvidence(
  source: RetrievedSource,
  documentTitle = "Research document",
): ResearchEvidence {
  const normalizedSnippet =
    typeof source.snippet === "string" && source.snippet.trim()
      ? source.snippet.trim()
      : null;

  return {
    id: `${source.id}-${source.chunk_index ?? "unknown"}`,
    source,
    documentId: source.document_id ?? null,
    documentTitle,
    pageNumber: source.page_number,
    quote: normalizedSnippet,
    technicalDetails: {
      chunkIndex: source.chunk_index,
      distance: source.distance,
    },
  };
}

export interface ResearchSessionState {
  chat: ChatSession | null;
  documents: ResearchDocument[];
  activeDocument: ResearchDocument | null;
  messages: ChatMessage[];
  evidence: ResearchEvidence[];
  researchMode: ResearchMode;
  model: AIModel;
  provider: AIProvider;
  documentPreparation: DocumentPreparationState | null;
}

export interface ResearchSession {
  id: number;
  title: string;
  mode: ResearchMode;
  chat: ChatSession;
  documents: ResearchDocument[];
  activeDocumentId: number | null;
  createdAt: string;
  updatedAt: string;
}

export const RESEARCH_MODE_LABELS: Record<ResearchMode, string> = {
  academic: "Academic",
  legal: "Legal",
  general: "General",
  simple: "Simple",
};

export const RESEARCH_MODE_DESCRIPTIONS: Record<ResearchMode, string> = {
  academic:
    "Analyze claims, methodology, evidence, limitations, and scholarly arguments.",
  legal:
    "Focus on exact language, obligations, conditions, exceptions, and supporting evidence.",
  general:
    "Explore documents and questions with balanced, structured answers.",
  simple:
    "Explain complex material in clear, accessible language.",
};

export const DOCUMENT_PREPARATION_LABELS: Record<
  DocumentPreparationStage,
  string
> = {
  uploading: "Uploading",
  extracting: "Extracting Text",
  indexing: "Indexing Evidence",
  ready: "Ready",
  failed: "Failed",
};
