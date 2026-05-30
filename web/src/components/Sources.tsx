import { useState } from "react";
import type { Source } from "../types";

export function Sources({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <div className="sources">
      <button
        className="sources-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "▾" : "▸"} Sources ({sources.length})
      </button>
      {open && (
        <ul className="sources-list">
          {sources.map((s, i) => (
            <li key={`${s.doc_id ?? s.label}-${i}`} className="source">
              <span className="source-label">{s.label}</span>
              {s.page != null && <span className="source-meta">p.{s.page}</span>}
              {s.score != null && (
                <span className="source-score" title="relevance score">
                  {s.score.toFixed(2)}
                </span>
              )}
              {s.snippet && <p className="source-snippet">{s.snippet}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
