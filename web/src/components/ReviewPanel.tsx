import { useCallback, useEffect, useState } from "react";
import { approve, getApiKey, listPending, reject, setApiKey } from "../lib/api";
import type { PendingReview } from "../types";

/**
 * Operator panel for the `learning_review` queue.
 *
 * Lists answers awaiting moderation and lets an operator Approve (embed into the
 * knowledge base) or Reject (discard) each one, removing it optimistically on
 * success. Review writes are gated by `require_api_key` when the server runs with
 * REQUIRE_AUTH_FOR_INGEST=true, so an API-key field is included; the key is kept
 * in localStorage and sent as X-API-Key. This panel is intended for operators.
 */
export function ReviewPanel() {
  const [items, setItems] = useState<PendingReview[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [cursor, setCursor] = useState<number | null>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [apiKey, setApiKeyState] = useState(getApiKey());
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(async (from: number, append: boolean) => {
    setLoading(true);
    setError("");
    try {
      const r = await listPending(from);
      setItems((prev) => (append ? [...prev, ...r.pending] : r.pending));
      setTotal(r.total);
      setCursor(r.next_cursor ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(0, false);
  }, [load]);

  function saveKey() {
    setApiKey(apiKey.trim());
    setApiKeyState(apiKey.trim());
    load(0, false);
  }

  async function decide(entryId: string, action: "approve" | "reject") {
    setPendingId(entryId);
    setError("");
    try {
      await (action === "approve" ? approve(entryId) : reject(entryId));
      // Optimistically drop the resolved entry from the list.
      setItems((prev) => prev.filter((it) => it.entry_id !== entryId));
      setTotal((t) => (t == null ? t : Math.max(0, t - 1)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPendingId(null);
    }
  }

  return (
    <section className="review" aria-label="Learning review queue">
      <div className="review-bar">
        <p className="review-note">
          Operator panel — approve to embed an answer into the knowledge base, reject to
          discard it.
        </p>
        <label className="control">
          <span className="control-label">API key</span>
          <input
            type="password"
            className="review-key"
            value={apiKey}
            placeholder="X-API-Key"
            autoComplete="off"
            onChange={(e) => setApiKeyState(e.target.value)}
            onBlur={saveKey}
            onKeyDown={(e) => e.key === "Enter" && saveKey()}
            aria-label="Operator API key"
          />
        </label>
        <button type="button" className="btn btn-upload" disabled={loading} onClick={() => load(0, false)}>
          Refresh
        </button>
      </div>

      {error && (
        <p className="review-error" role="alert">
          {error}
        </p>
      )}

      {loading && items.length === 0 ? (
        <p className="review-status" role="status">
          Loading…
        </p>
      ) : items.length === 0 ? (
        <p className="review-status">No entries awaiting review.</p>
      ) : (
        <>
          <p className="review-status">
            {total ?? items.length} pending{total != null && total !== items.length ? ` (${items.length} loaded)` : ""}
          </p>
          <ul className="review-list">
            {items.map((it) => (
              <li key={it.entry_id} className="review-item">
                <div className="review-meta">
                  {it.best_score != null && (
                    <span className="source-score" title="best retrieval score">
                      {it.best_score.toFixed(2)}
                    </span>
                  )}
                  <span className="review-time">{new Date(it.created_at).toLocaleString()}</span>
                </div>
                <p className="review-q">{it.question}</p>
                <p className="review-a">{it.answer}</p>
                <div className="review-actions">
                  <button
                    type="button"
                    className="btn btn-send"
                    disabled={pendingId === it.entry_id}
                    onClick={() => decide(it.entry_id, "approve")}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn btn-stop"
                    disabled={pendingId === it.entry_id}
                    onClick={() => decide(it.entry_id, "reject")}
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {cursor != null && (
            <button
              type="button"
              className="btn btn-upload review-more"
              disabled={loading}
              onClick={() => load(cursor, true)}
            >
              {loading ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
