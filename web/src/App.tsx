import { useEffect, useState } from "react";
import { Composer } from "./components/Composer";
import { Controls } from "./components/Controls";
import { HealthBadge } from "./components/HealthBadge";
import { MessageList } from "./components/MessageList";
import { ReviewPanel } from "./components/ReviewPanel";
import { UploadButton } from "./components/UploadButton";
import { useChatStream } from "./lib/useChatStream";
import type { Lang, Mode } from "./types";

function userId(): string {
  const k = "chatbot:user-id";
  let id = localStorage.getItem(k);
  if (!id) {
    id = `web-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(k, id);
  }
  return id;
}

export function App() {
  const [mode, setMode] = useState<Mode>("strict");
  const [lang, setLang] = useState<Lang>("auto");
  const [review, setReview] = useState(() => window.location.hash === "#/review");
  const [editText, setEditText] = useState<string | null>(null);
  const { messages, busy, send, stop } = useChatStream(userId());

  useEffect(() => {
    const onHash = () => setReview(window.location.hash === "#/review");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const toggleReview = () => {
    window.location.hash = review ? "" : "#/review";
  };

  const sendWithOverrides = (text: string) => send(text, { mode, lang });

  const handleEdit = (text: string) => setEditText(text);

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">Chatbot</h1>
        <div className="header-right">
          {!review && (
            <>
              <Controls mode={mode} lang={lang} disabled={busy} onMode={setMode} onLang={setLang} />
              <UploadButton userId={userId()} disabled={busy} />
            </>
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
            <MessageList messages={messages} onResend={send} onEdit={handleEdit} />
          </main>
          <footer className="footer">
            <Composer
              busy={busy}
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
