export type ResearchStatus =
  | "queued"
  | "running"
  | "retrieving"
  | "synthesizing"
  | "validating"
  | "completed"
  | "failed"
  | "cancelled";

export const ACTIVE_RESEARCH_STATUSES: ReadonlySet<ResearchStatus> = new Set([
  "queued",
  "running",
  "retrieving",
  "synthesizing",
  "validating",
]);

export interface ResearchCitation {
  citation_id: string;
  document_id: number;
  filename: string;
  chunk_id: number;
  page_number: number | null;
  excerpt: string;
}

export interface ResearchFacets {
  methodology: string;
  datasets: string;
  metrics: string;
  findings: string;
  limitations: string;
}

export interface ResearchRunLifecycleMetadata {
  correlation_id?: string | null;
  cancel_requested?: boolean;
  attempt_count?: number;
  stage_timestamps?: Record<string, string>;
  error_code?: string | null;
  updated_at?: string;
}

export interface ResearchRun {
  id: number;
  workspace_id: number;
  requester_id: number;
  query: string;
  status: ResearchStatus;
  answer: string | null;
  facets?: ResearchFacets | null;
  citations: ResearchCitation[];
  run_metadata: Record<string, unknown> & {
    selected_document_ids?: number[];
    lifecycle?: ResearchRunLifecycleMetadata;
  };
  created_at: string;
  completed_at: string | null;
  error_message?: string | null;
}

export interface CreateResearchRunInput {
  query: string;
  document_ids: number[];
}

export interface ResearchRunListResponse {
  items: ResearchRun[];
  total: number;
}

export interface ResearchRunCancelResponse {
  id: number;
  workspace_id: number;
  status: ResearchStatus;
  cancel_requested: boolean;
  message: string;
}

export interface ResearchRunStageEvent {
  run_id: number;
  workspace_id: number;
  status: ResearchStatus;
  stage: ResearchStatus;
  progress_percent: number;
  cancel_requested: boolean;
  attempt_count: number;
  correlation_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  updated_at: string;
}
