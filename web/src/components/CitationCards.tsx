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
          {sources.map((s, i) => {
            // Build the page range string once for use in header and copy-to-clipboard.
            const pageRange =
              s.page != null
                ? s.page_end != null && s.page_end > s.page
                  ? `pp. ${s.page}–${s.page_end}`
                  : `p. ${s.page}`
                : null;

            return (
              <li key={`${s.doc_id ?? s.label}-${i}`} className="citation" tabIndex={-1}>
                <div className="citation-header">
                  <span className="citation-label">{s.label}</span>
                  {/* Element type badge — omit for "paragraph" (implicit default). 9.7: text
                      content only, React escapes by default — no XSS surface. */}
                  {s.element_type != null && s.element_type !== "paragraph" && (
                    <span className="citation-element-type">{s.element_type}</span>
                  )}
                  {pageRange != null && (
                    <span className="citation-page">{pageRange}</span>
                  )}
                  {s.score != null && <ScoreMeter value={s.score} />}
                </div>
                {/* Section title below the document label, lighter weight. */}
                {s.section != null && (
                  <div className="citation-section">{s.section}</div>
                )}
                {s.snippet && (
                  <details className="citation-details">
                    <summary className="citation-snippet-toggle" tabIndex={0}>Show snippet</summary>
                    <p className="citation-snippet">{s.snippet}</p>
                  </details>
                )}
                {/* Bbox debug view — values rendered as toFixed(2) strings (9.8). */}
                {s.bbox != null && s.bbox.length === 4 && (
                  <details className="citation-bbox">
                    <summary className="citation-bbox-toggle">bbox</summary>
                    <code className="citation-bbox-values">
                      [{s.bbox.map((v) => v.toFixed(2)).join(", ")}]
                    </code>
                  </details>
                )}
                <button
                  type="button"
                  className="citation-copy"
                  tabIndex={0}
                  onClick={() => {
                    const text = [
                      s.label,
                      s.section,
                      pageRange,
                      s.element_type,
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
            );
          })}
        </ul>
      )}
    </div>
  );
}
