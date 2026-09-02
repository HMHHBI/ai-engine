export type Role = "user" | "ai" | "system";

export type AIProvider = "gemini" | "ollama" | "openai";

export type AIModel =
  | "gemini-2.5-flash"
  | "llama3.2"
  | "deepseek-r1"
  | "gpt-4o-mini";

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
}

export interface ChatMessage {
  id?: number;
  chat_id?: number;
  role: Role;
  content: string;
  created_at?: string;
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
  prompt: string;
  model?: AIModel;
  provider?: AIProvider;
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