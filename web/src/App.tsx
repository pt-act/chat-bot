import { useCallback, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { Controls } from "./components/Controls";
import { HealthBadge } from "./components/HealthBadge";
import { MessageList } from "./components/MessageList";
import { UploadButton } from "./components/UploadButton";
import { streamChat } from "./lib/api";
import type { ChatMessage, Lang, Mode, Source } from "./types";

// Stable per-browser id so conversation memory persists across reloads.
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<Mode>("strict");
  const [lang, setLang] = useState<Lang>("auto");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patchLast = useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      const next = prev.slice();
      next[next.length - 1] = fn(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = useCallback(
    (text: string) => {
      const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text };
      const assistant: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        streaming: true,
        sources: [],
      };
      setMessages((prev) => [...prev, userMsg, assistant]);
      setBusy(true);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      streamChat(
        { q: text, mode, lang },
        userId(),
        {
          onToken: (delta) => patchLast((m) => ({ ...m, content: m.content + delta })),
          onSources: (sources: Source[]) => patchLast((m) => ({ ...m, sources })),
          onDone: (meta) => {
            patchLast((m) => ({ ...m, streaming: false, meta: meta as unknown as ChatMessage["meta"] }));
            setBusy(false);
          },
          onError: (message) => {
            patchLast((m) => ({
              ...m,
              streaming: false,
              error: true,
              content: m.content || message,
            }));
            setBusy(false);
          },
        },
        ctrl.signal,
      );
    },
    [mode, lang, patchLast],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    patchLast((m) => ({ ...m, streaming: false }));
    setBusy(false);
  }, [patchLast]);

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">Chatbot</h1>
        <div className="header-right">
          <Controls mode={mode} lang={lang} disabled={busy} onMode={setMode} onLang={setLang} />
          <UploadButton userId={userId()} disabled={busy} />
          <HealthBadge />
        </div>
      </header>
      <main className="main">
        <MessageList messages={messages} />
      </main>
      <footer className="footer">
        <Composer busy={busy} onSend={send} onStop={stop} />
      </footer>
    </div>
  );
}
