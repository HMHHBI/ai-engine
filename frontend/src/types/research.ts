export type ResearchStatus = "queued" | "running" | "completed" | "failed";

export interface ResearchCitation {
  citation_id: string;
  document_id: number;
  filename: string;
  chunk_id: number;
  page_number: number | null;
  excerpt: string;
}

export interface ResearchRun {
  id: number;
  workspace_id: number;
  requester_id: number;
  query: string;
  status: ResearchStatus;
  answer: string | null;
  citations: ResearchCitation[];
  run_metadata: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
  error_message?: string | null;
}

export interface CreateResearchRunInput {
  query: string;
  document_ids: number[];
}
