import type { Lang, Mode, Source } from "../types";

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

/**
 * POST /api/v1/chat/stream and parse the Server-Sent Events stream.
 *
 * EventSource only supports GET, so we read the response body as a stream and
 * parse SSE frames manually. `signal` lets the composer's Stop button abort.
 */
export async function streamChat(
  body: ChatBody,
  userId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch("/api/v1/chat/stream", {
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

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        dispatchFrame(frame, handlers);
      }
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") handlers.onError("Stream interrupted.");
  }
}

function dispatchFrame(frame: string, handlers: StreamHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;
  let data: any;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  switch (event) {
    case "token":
      if (typeof data.delta === "string") handlers.onToken(data.delta);
      break;
    case "sources":
      handlers.onSources(data.sources ?? []);
      break;
    case "done":
      handlers.onDone(data.meta ?? {});
      break;
    case "error":
      handlers.onError(data.title ?? "Server error.");
      break;
  }
}

export interface UploadResult {
  doc_id: string;
  status: string;
}

/**
 * Upload a local PDF to POST /api/v1/ingest/upload (multipart/form-data).
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
      headers: { "X-User-Id": userId },
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
