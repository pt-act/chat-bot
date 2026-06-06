export type Mode = "strict" | "open" | "learning" | "learning_review";
export type Lang = "auto" | "en" | "ar" | "pt";

export interface Source {
  label: string;
  doc_id?: string | null;
  score?: number | null;
  page?: number | null;
  snippet?: string | null;
}

export type Groundedness = "supported" | "partial" | "unsupported";

export interface ChatMeta {
  mode: string;
  lang?: string | null;
  self_ingested?: boolean;
  grounded?: Groundedness | null;
  grounded_score?: number | null;
  correlation_id?: string | null;
  model?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  meta: ChatMeta;
}

export interface ChatErrorMeta {
  status?: number;
  retryAfter?: number;
  title?: string;
  detail?: string;
  correlation_id?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  meta?: ChatMeta;
  streaming?: boolean;
  error?: boolean;
  errorMeta?: ChatErrorMeta;
}

// --- Reviewer queue (operator panel) ---

/** A pending entry awaiting moderator approval in the learning_review queue. */
export interface PendingReview {
  entry_id: string;
  question: string;
  answer: string;
  best_score?: number | null;
  created_at: string;
  status: string;
}

/** GET /api/v1/review/pending response. */
export interface PendingListResponse {
  total: number;
  pending: PendingReview[];
  next_cursor?: number | null;
}

/** POST /api/v1/review/{id}/approve|reject response. */
export interface ReviewDecision {
  entry_id: string;
  status: "approved" | "rejected";
  embedded: boolean;
}
