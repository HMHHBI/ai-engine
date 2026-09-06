export type Role = "user" | "ai" | "system";

export type AIProvider = "gemini" | "ollama" | "openai";

export type AIModel =
  | "gemini-2.5-flash"
  | "llama3.2"
  | "deepseek-r1"
  | "gpt-4o-mini";

export type ChatTask = "general" | string;

export interface RetrievedSource {
  id: number;
  page_number: number | null;
  chunk_index: number | null;
  distance: number;
}

export interface User {
  id: number;
  email: string;
  name: string | null;
  picture: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ChatSession {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
  updated_at: string;
  has_pdf?: boolean;
  persona?: ChatPersona;
  custom_instructions?: string | null;
}

export interface ChatMessage {
  id?: number;
  chat_id?: number;
  role: Role;
  content: string;
  text?: string;
  image_data?: string | null;
  created_at?: string;
  sources?: RetrievedSource[];
}

export interface ChatDetailsResponse {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
  has_pdf: boolean;
  pdf_filename?: string | null;
}

export interface StreamPayload {
  chat_id: number;
  prompt: string;
  task?: ChatTask;
  model?: AIModel;
  provider?: AIProvider;
  file_context?: string;
  image_base64?: string[];
  image_mime?: string[];
}

export interface UploadPdfResponse {
  message: string;
  chat_id: number;
  filename: string;
  chunks_count: number;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

export interface GoogleAuthPayload {
  credential?: string;
  token?: string;
}

export type ChatPersona =
  | "default"
  | "academic"
  | "developer"
  | "legal"
  | "simple";

export interface ChatPersonaUpdate {
  persona?: ChatPersona;
  custom_instructions?: string | null;
}

export interface ChatDetailsResponse {
  id: number;
  title: string;
  pdf_context: string | null;
  ai_provider: string | null;
  ai_model: string | null;
  embedding_provider: string | null;
  persona: ChatPersona;
  custom_instructions: string | null;
}

export type DocumentStatus = "processing" | "ready" | "failed";

export interface Document {
  id: number;
  user_id: number;
  chat_id: number;
  filename: string;
  mime_type: string;
  file_size: number | null;
  page_count: number | null;
  storage_url: string | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentSummary {
  id: number;
  chat_id: number;
  filename: string;
  mime_type: string;
  file_size: number | null;
  page_count: number | null;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
}

export interface DocumentMetadataUpdate {
  filename?: string;
  mime_type?: string;
  file_size?: number | null;
  page_count?: number | null;
  storage_url?: string | null;
}

export interface PdfUploadResponse {
  status: string;
  filename: string;
  pdf_context?: string;
  chunks_total: number;
  chunks_indexed: number;
  chunks_failed: number;
  embedding_provider: string;
  message: string;
  document?: DocumentSummary | Document;
}