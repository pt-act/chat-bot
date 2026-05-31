export type Mode = "strict" | "open" | "learning" | "learning_review";
export type Lang = "auto" | "en" | "ar" | "pt";

export interface Source {
  label: string;
  doc_id?: string | null;
  score?: number | null;
  page?: number | null;
  snippet?: string | null;
}

export interface ChatMeta {
  mode: string;
  lang?: string | null;
  self_ingested?: boolean;
  correlation_id?: string | null;
  model?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  meta: ChatMeta;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  meta?: ChatMeta;
  streaming?: boolean;
  error?: boolean;
}
