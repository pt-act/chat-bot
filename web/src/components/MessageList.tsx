import { useEffect, useRef } from "react";
import type { ChatMessage } from "../types";
import { dirFor } from "../lib/rtl";
import { Sources } from "./Sources";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the latest content as it streams in.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="empty" role="note">
        <p className="empty-title">Ask about our policies</p>
        <p className="empty-hint">e.g. “What is the return window?” · “ما هي سياسة الإرجاع؟”</p>
      </div>
    );
  }

  return (
    <div className="messages">
      {messages.map((m) => (
        <article
          key={m.id}
          className={`bubble bubble-${m.role}${m.error ? " bubble-error" : ""}`}
          dir={dirFor(m.content)}
          aria-live={m.streaming ? "polite" : undefined}
        >
          <div className="bubble-body">{m.content || (m.streaming ? "…" : "")}</div>
          {m.role === "assistant" && m.sources && <Sources sources={m.sources} />}
          {m.meta?.self_ingested && (
            <span className="badge-learn" title="This answer was saved to the learning store.">
              learned
            </span>
          )}
        </article>
      ))}
      <div ref={endRef} />
    </div>
  );
}
