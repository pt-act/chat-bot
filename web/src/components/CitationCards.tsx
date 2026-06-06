import { useCallback, useRef, useState } from "react";
import type { Source } from "../types";

interface Props {
  sources: Source[];
}

function ScoreMeter({ value }: { value: number }) {
  return (
    <span className="score-meter" title={`score: ${value.toFixed(2)}`}>
      <span className="score-meter-fill" style={{ width: `${Math.round(value * 100)}%` }} />
    </span>
  );
}

export function CitationCards({ sources }: Props) {
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLUListElement>) => {
    if (!listRef.current || e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = Array.from(listRef.current.querySelectorAll<HTMLElement>(".citation-copy, .citation-snippet-toggle"));
    const current = document.activeElement as HTMLElement | null;
    const idx = items.indexOf(current ?? (undefined as unknown as HTMLElement));
    if (e.key === "ArrowDown") {
      const next = items[idx + 1] ?? items[0];
      next?.focus();
    } else {
      const prev = items[idx - 1] ?? items[items.length - 1];
      prev?.focus();
    }
  }, []);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="citations">
      <button
        className="citations-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "▾" : "▸"} Sources ({sources.length})
      </button>
      {open && (
        <ul className="citations-list" ref={listRef} onKeyDown={handleKeyDown}>
          {sources.map((s, i) => (
            <li key={`${s.doc_id ?? s.label}-${i}`} className="citation" tabIndex={-1}>
              <div className="citation-header">
                <span className="citation-label">{s.label}</span>
                {s.page != null && <span className="citation-page">p.{s.page}</span>}
                {s.score != null && <ScoreMeter value={s.score} />}
              </div>
              {s.snippet && (
                <details className="citation-details">
                  <summary className="citation-snippet-toggle" tabIndex={0}>Show snippet</summary>
                  <p className="citation-snippet">{s.snippet}</p>
                </details>
              )}
              <button
                type="button"
                className="citation-copy"
                tabIndex={0}
                onClick={() => {
                  const text = [
                    s.label,
                    s.page != null && `p.${s.page}`,
                    s.score != null && `score: ${s.score.toFixed(2)}`,
                    s.snippet,
                  ]
                    .filter(Boolean)
                    .join(" | ");
                  navigator.clipboard.writeText(text);
                }}
              >
                Copy
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
