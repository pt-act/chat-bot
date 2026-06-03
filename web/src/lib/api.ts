/// <reference types="vite/client" />
import type {
  Lang,
  Mode,
  PendingListResponse,
  ReviewDecision,
  Source,
} from "../types";

// --- API key (operator) ---
// Review writes (and ingest, when REQUIRE_AUTH_FOR_INGEST=true) are gated by
// `require_api_key`, sent as the X-API-Key header. The key is stored locally so
// an operator only enters it once per browser.
const API_KEY_STORAGE = "chatbot.apiKey";

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  if (key) localStorage.setItem(API_KEY_STORAGE, key);
  else localStorage.removeItem(API_KEY_STORAGE);
}

/** Headers for a privileged call: adds X-API-Key only when a key is stored. */
function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const key = getApiKey();
  return key ? { ...extra, "X-API-Key": key } : extra;
}

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onSources: (sources: Source[]) => void;
  onDone: (meta: Record<string, unknown>) => void;
  onError: (message: string) => void;
}

interface ChatBody {
  q: string;
  mode?: Mode;
  lang?: Lang;
  top_k?: number;
  score_threshold?: number;
}

const API_BASE = import.meta.env.DEV ? "http://localhost:8000" : "";

/**
 * POST /api/v1/chat/stream and parse the Server-Sent Events stream.
 *
 * In dev mode we hit the backend directly on port 8000 to bypass Vite's
 * http-proxy, which buffers SSE chunks and drops early `token` frames.
 * CORS must allow http://localhost:5173 (set CORS_ORIGINS in .env).
 *
 * EventSource only supports GET, so we read the response body as a stream and
 * parse SSE frames manually. `signal` lets the composer's Stop button abort.
 *
 * Frames can be split across multiple `read()` calls, so we buffer until we
 * see a blank line (`\n\n`) which marks the end of an SSE frame.
 */
export async function streamChat(
  body: ChatBody,
  userId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-User-Id": userId },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    handlers.onError("Network error — could not reach the server.");
    return;
  }

  if (resp.status === 429) {
    const retry = resp.headers.get("Retry-After") ?? "a few";
    handlers.onError(`Rate limited. Try again in ${retry}s.`);
    return;
  }
  if (!resp.ok || !resp.body) {
    handlers.onError(`Request failed (${resp.status}).`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatchFrame(frame: string): boolean {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return true;
    let data: any;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return true;
    }
    if (event === "token" && typeof data.delta === "string") {
      handlers.onToken(data.delta);
    } else if (event === "sources") {
      handlers.onSources(data.sources ?? []);
    } else if (event === "done") {
      handlers.onDone(data.meta ?? {});
      return false;
    } else if (event === "error") {
      handlers.onError(data.title ?? "Server error.");
      return false;
    }
    return true;
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (!dispatchFrame(frame)) return;
      }
    }

    if (buffer.trim()) {
      dispatchFrame(buffer);
    }
  } catch (e: any) {
    if (e.name !== "AbortError") {
      handlers.onError("Stream interrupted.");
    }
  }
}

export interface UploadResult {
  doc_id: string;
  status: string;
}

/**
 * Upload a local document (PDF/TXT/MD/DOCX/HTML) to POST /api/v1/ingest/upload (multipart/form-data).
 *
 * The document is sent straight from the user's machine — no URL, nothing leaves
 * their environment except the file itself. Returns the queued ingest result, or
 * throws with a human-readable message on failure.
 */
export async function uploadDocument(file: File, userId: string): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);

  let resp: Response;
  try {
    // Note: do NOT set Content-Type — the browser adds the multipart boundary.
    resp = await fetch("/api/v1/ingest/upload", {
      method: "POST",
      headers: authHeaders({ "X-User-Id": userId }),
      body: form,
    });
  } catch {
    throw new Error("Network error — could not reach the server.");
  }

  if (!resp.ok) {
    let detail = `Upload failed (${resp.status}).`;
    try {
      const body = await resp.json();
      detail = body.detail || body.title || detail;
    } catch {
      // non-JSON error body; keep the generic message
    }
    throw new Error(detail);
  }
  return (await resp.json()) as UploadResult;
}

export interface Health {
  status: string;
  dependencies: Record<string, string>;
}

export async function getHealth(): Promise<Health | null> {
  try {
    const r = await fetch("/health");
    if (!r.ok) return null;
    return (await r.json()) as Health;
  } catch {
    return null;
  }
}

// --- Reviewer queue (operator) ---

/** Turn a non-OK review response into a human-readable Error. */
async function reviewError(resp: Response): Promise<Error> {
  if (resp.status === 401 || resp.status === 403) {
    return new Error("Unauthorized — check the operator API key.");
  }
  let detail = `Request failed (${resp.status}).`;
  try {
    const body = await resp.json();
    detail = body.detail || body.title || detail;
  } catch {
    // non-JSON error body; keep the generic message
  }
  return new Error(detail);
}

/**
 * GET /api/v1/review/pending — list entries awaiting moderation.
 *
 * Sends X-API-Key when an operator key is stored (the route is gated by
 * `require_api_key` when REQUIRE_AUTH_FOR_INGEST=true).
 */
export async function listPending(cursor = 0, limit = 50): Promise<PendingListResponse> {
  let resp: Response;
  try {
    resp = await fetch(`/api/v1/review/pending?limit=${limit}&cursor=${cursor}`, {
      headers: authHeaders(),
    });
  } catch {
    throw new Error("Network error — could not reach the server.");
  }
  if (!resp.ok) throw await reviewError(resp);
  return (await resp.json()) as PendingListResponse;
}

/** POST /api/v1/review/{entry_id}/approve — embed the answer into the KB. */
export async function approve(entryId: string): Promise<ReviewDecision> {
  return decide(entryId, "approve");
}

/** POST /api/v1/review/{entry_id}/reject — discard the pending answer. */
export async function reject(entryId: string): Promise<ReviewDecision> {
  return decide(entryId, "reject");
}

async function decide(entryId: string, action: "approve" | "reject"): Promise<ReviewDecision> {
  let resp: Response;
  try {
    resp = await fetch(`/api/v1/review/${encodeURIComponent(entryId)}/${action}`, {
      method: "POST",
      headers: authHeaders(),
    });
  } catch {
    throw new Error("Network error — could not reach the server.");
  }
  if (!resp.ok) throw await reviewError(resp);
  return (await resp.json()) as ReviewDecision;
}
