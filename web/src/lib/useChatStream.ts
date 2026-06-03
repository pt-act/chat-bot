import { useCallback, useRef, useState } from "react";
import { streamChat } from "./api";
import type { ChatMessage, Lang, Mode, Source } from "../types";

export interface UseChatStreamReturn {
  messages: ChatMessage[];
  busy: boolean;
  send: (text: string, overrides?: { mode?: Mode; lang?: Lang }) => void;
  stop: () => void;
  patchLast: (fn: (m: ChatMessage) => ChatMessage) => void;
}

export function useChatStream(userId: string): UseChatStreamReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patchLast = useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.slice();
      next[next.length - 1] = fn(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = useCallback(
    (text: string, overrides?: { mode?: Mode; lang?: Lang }) => {
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
        { q: text, mode: overrides?.mode, lang: overrides?.lang },
        userId,
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
    [userId, patchLast],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    patchLast((m) => ({ ...m, streaming: false }));
    setBusy(false);
  }, [patchLast]);

  return { messages, busy, send, stop, patchLast };
}
