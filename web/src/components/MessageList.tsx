import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import { dirFor, langFor } from "../lib/rtl";
import { ActionRow } from "./ActionRow";
import { CitationCards } from "./CitationCards";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { MarkdownBody } from "./MarkdownBody";
import { ModeChip, ProvenanceChip } from "./Chips";
import { RefusalCard } from "./RefusalCard";
import { StreamingIndicator } from "./StreamingIndicator";

const STRICT_REFUSAL_RE = /I don't have information|I don't have any (information|documents)|not in (the )?knowledge base|I cannot (answer|provide|find)/i;

interface Props {
  messages: ChatMessage[];
  onResend?: (q: string, overrides?: Record<string, unknown>) => void;
  onEdit?: (text: string) => void;
}

export function MessageList({ messages, onResend, onEdit }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    setPinned(atBottom);
  };

  useEffect(() => {
    if (pinned) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pinned]);

  if (messages.length === 0) {
    return (
      <div className="empty" role="note">
        <p className="empty-title">Ask about our policies</p>
        <p className="empty-hint">
          e.g. "What is the return window?" · "ما هي سياسة الإرجاع؟"
        </p>
      </div>
    );
  }

  function bestScore(m: ChatMessage): number | null {
    const grounded = m.meta?.grounded_score;
    if (grounded != null) return grounded;
    const srcScores = m.sources?.map((s) => s.score).filter((s): s is number => s != null) ?? [];
    return srcScores.length > 0 ? Math.max(...srcScores) : null;
  }

  function isStrictRefusal(m: ChatMessage): boolean {
    if (m.meta?.mode !== "strict") return false;
    if (m.streaming) return false;
    if (m.sources && m.sources.length > 0) return false;
    return STRICT_REFUSAL_RE.test(m.content);
  }

  function prevQuestion(msgs: ChatMessage[], index: number): string | null {
    for (let i = index - 1; i >= 0; i--) {
      if (msgs[i].role === "user") return msgs[i].content;
    }
    return null;
  }

  const lastAssistantIdx = [...messages]
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.role === "assistant" && !m.streaming)
    .pop()?.i;

  return (
    <div className="main-inner" ref={scrollRef} onScroll={handleScroll}>
      <div className="messages">
        {messages.map((m, i) => {
          const dir = dirFor(m.content);
          const lang = langFor(m.meta?.lang ?? null, m.content);
          const showRefusal = m.role === "assistant" && isStrictRefusal(m);
          const question = showRefusal ? prevQuestion(messages, i) : null;
          const isLastAssistant = i === lastAssistantIdx;

          if (m.role === "user") {
            return (
              <article key={m.id} className="bubble bubble-user" dir={dir} lang={lang}>
                <div className="bubble-body">{m.content}</div>
                <ActionRow
                  isLastAssistant={false}
                  isStreaming={false}
                  onRegenerate={() => {}}
                  userText={m.content}
                  onEdit={onEdit}
                />
              </article>
            );
          }

          return (
            <article
              key={m.id}
              className={`bubble bubble-assistant${m.error ? " bubble-error" : ""}`}
              dir={dir}
              lang={lang}
              aria-live={!m.streaming && !m.error ? "polite" : undefined}
            >
              {!m.streaming && !m.error && (
                <div className="bubble-meta">
                  <ConfidenceBadge score={bestScore(m)} />
                  <ModeChip mode={m.meta?.mode ?? "strict"} />
                  <ProvenanceChip selfIngessed={m.meta?.self_ingested ?? false} />
                </div>
              )}
              <StreamingIndicator
                streaming={m.streaming ?? false}
                hasContent={m.content.length > 0}
                error={m.error && !m.content}
              />
              {m.content ? (
                <MarkdownBody content={m.content} streaming={m.streaming ?? false} />
              ) : null}
              {showRefusal && question && onResend && (
                <RefusalCard question={question} onResend={onResend} />
              )}
              {m.role === "assistant" && m.sources && <CitationCards sources={m.sources} />}
              <ActionRow
                isLastAssistant={isLastAssistant}
                isStreaming={m.streaming ?? false}
                onRegenerate={() => {
                  const q = prevQuestion(messages, i);
                  if (q && onResend) onResend(q, {});
                }}
              />
            </article>
          );
        })}
        <div ref={endRef} />
      </div>
      {!pinned && (
        <button
          type="button"
          className="new-msg-affordance"
          onClick={() => {
            setPinned(true);
            endRef.current?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          ↓ New messages
        </button>
      )}
    </div>
  );
}
