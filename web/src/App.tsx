import { useEffect, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { Controls } from "./components/Controls";
import { HealthBadge } from "./components/HealthBadge";
import { MessageList } from "./components/MessageList";
import { ReviewPanel } from "./components/ReviewPanel";
import { UploadButton } from "./components/UploadButton";
import { useChatStream } from "./lib/useChatStream";
import type { ChatMessage, Lang, Mode } from "./types";

const USER_ID_KEY = "chatbot:user-id";
const SESSION_MODE_KEY = "chatbot:mode";
const SESSION_LANG_KEY = "chatbot:lang";

function generateUserId(): string {
  return `web-${Math.random().toString(36).slice(2, 10)}`;
}

function loadUserId(): string {
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = generateUserId();
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}

function loadSessionMode(): Mode {
  const v = sessionStorage.getItem(SESSION_MODE_KEY) as Mode | null;
  if (v && ["strict", "open", "learning", "learning_review"].includes(v)) return v;
  return "strict";
}

function loadSessionLang(): Lang {
  const v = sessionStorage.getItem(SESSION_LANG_KEY) as Lang | null;
  if (v && ["auto", "en", "ar", "pt"].includes(v)) return v;
  return "auto";
}

function exportTranscript(messages: ChatMessage[], format: "json" | "text") {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `chat-transcript-${timestamp}.${format === "json" ? "json" : "txt"}`;

  let content: string;
  if (format === "json") {
    content = JSON.stringify(messages, null, 2);
  } else {
    content = messages
      .map((m) => {
        const role = m.role === "user" ? "You" : "Assistant";
        return `[${role}]\n${m.content}\n`;
      })
      .join("\n");
  }

  const blob = new Blob([content], { type: format === "json" ? "application/json" : "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function SrAnnouncer({ messages }: { messages: ChatMessage[] }) {
  const [announcement, setAnnouncement] = useState("");
  const lastCompletedRef = useRef<string | null>(null);

  useEffect(() => {
    const completed = messages
      .filter((m) => m.role === "assistant" && !m.streaming && !m.error && m.content)
      .pop();
    if (completed && completed.id !== lastCompletedRef.current) {
      lastCompletedRef.current = completed.id;
      // Trim to first sentence or 150 chars for brevity in SR
      const text = completed.content.slice(0, 150).replace(/\n/g, " ");
      setAnnouncement(`Assistant: ${text}${completed.content.length > 150 ? "…" : ""}`);
    }
  }, [messages]);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="sr-announcer"
      style={{ position: "absolute", left: "-10000px", width: "1px", height: "1px", overflow: "hidden" }}
    >
      {announcement}
    </div>
  );
}

export function App() {
  const [currentUserId, setCurrentUserId] = useState(loadUserId);
  const [mode, setMode] = useState<Mode>(loadSessionMode);
  const [lang, setLang] = useState<Lang>(loadSessionLang);
  const [review, setReview] = useState(() => window.location.hash === "#/review");
  const [editText, setEditText] = useState<string | null>(null);
  const [retryCountdown, setRetryCountdown] = useState<number>(0);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const { messages, busy, send, stop, reset } = useChatStream(currentUserId);

  useEffect(() => {
    const onHash = () => setReview(window.location.hash === "#/review");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    sessionStorage.setItem(SESSION_MODE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    sessionStorage.setItem(SESSION_LANG_KEY, lang);
  }, [lang]);

  // Rate-limit countdown from last error meta
  useEffect(() => {
    const lastErr = [...messages].reverse().find((m) => m.error && m.errorMeta?.retryAfter);
    if (lastErr?.errorMeta?.retryAfter) {
      const until = Date.now() + lastErr.errorMeta.retryAfter * 1000;
      const id = setInterval(() => {
        const remaining = Math.ceil((until - Date.now()) / 1000);
        if (remaining <= 0) {
          setRetryCountdown(0);
          clearInterval(id);
        } else {
          setRetryCountdown(remaining);
        }
      }, 1000);
      return () => clearInterval(id);
    }
    setRetryCountdown(0);
  }, [messages]);

  const toggleReview = () => {
    window.location.hash = review ? "" : "#/review";
  };

  const sendWithOverrides = (text: string) => {
    if (retryCountdown > 0) return;
    send(text, { mode, lang });
  };

  const handleEdit = (text: string) => setEditText(text);

  const handleNewChat = () => {
    const id = generateUserId();
    localStorage.setItem(USER_ID_KEY, id);
    setCurrentUserId(id);
    reset();
  };

  const isSendDisabled = busy || retryCountdown > 0;
  const hasMessages = messages.length > 0;

  return (
    <div className="app">
      <SrAnnouncer messages={messages} />
      <header className="header">
        <h1 className="title">Chatbot</h1>
        <div className="header-right">
          {!review && (
            <>
              <Controls mode={mode} lang={lang} disabled={busy} onMode={setMode} onLang={setLang} />
              <UploadButton userId={currentUserId} disabled={busy} />
            </>
          )}
          <button
            type="button"
            className="btn btn-new-chat"
            onClick={handleNewChat}
            title="Start a new conversation"
            disabled={busy}
          >
            + New
          </button>
          {hasMessages && !review && (
            <div className="export-dropdown">
              <button
                type="button"
                className="btn btn-export"
                onClick={() => setShowExportMenu((v) => !v)}
                title="Export transcript"
                aria-expanded={showExportMenu}
              >
                ↓ Export
              </button>
              {showExportMenu && (
                <div className="export-menu">
                  <button type="button" onClick={() => { exportTranscript(messages, "json"); setShowExportMenu(false); }}>
                    JSON
                  </button>
                  <button type="button" onClick={() => { exportTranscript(messages, "text"); setShowExportMenu(false); }}>
                    Text
                  </button>
                </div>
              )}
            </div>
          )}
          <button
            type="button"
            className="btn btn-upload"
            aria-pressed={review}
            onClick={toggleReview}
            title="Toggle the operator review queue"
          >
            {review ? "Chat" : "Review"}
          </button>
          <HealthBadge />
        </div>
      </header>
      {review ? (
        <main className="main">
          <ReviewPanel />
        </main>
      ) : (
        <>
          <main className="main">
            <MessageList
              messages={messages}
              onResend={send}
              onEdit={handleEdit}
              onSend={sendWithOverrides}
              mode={mode}
              lang={lang}
            />
          </main>
          <footer className="footer">
            {retryCountdown > 0 && (
              <div className="retry-countdown" role="status" aria-live="polite">
                Rate limit — retry in {retryCountdown}s
              </div>
            )}
            <div className="footer-meta">
              <span className="ttl-note">Conversations kept ~24 hours</span>
            </div>
            <Composer
              busy={isSendDisabled}
              onSend={sendWithOverrides}
              onStop={stop}
              editText={editText}
              onEditConsumed={() => setEditText(null)}
            />
          </footer>
        </>
      )}
    </div>
  );
}
