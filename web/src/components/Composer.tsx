import { useEffect, useRef, useState } from "react";

const MAX_CHARS = 2000;

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  editText?: string | null;
  onEditConsumed?: () => void;
}

export function Composer({ busy, onSend, onStop, editText, onEditConsumed }: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editText && !busy) {
      setText(editText);
      onEditConsumed?.();
      textareaRef.current?.focus();
    }
  }, [editText, busy, onEditConsumed]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || busy || trimmed.length > MAX_CHARS) return;
    onSend(trimmed);
    setText("");
  }

  const over = text.length > MAX_CHARS;
  const near = text.length > MAX_CHARS * 0.9;

  return (
    <form className="composer" onSubmit={submit}>
      <div className="composer-input-wrap">
        <textarea
          ref={textareaRef}
          className="composer-input"
          value={text}
          placeholder="Type a message…"
          aria-label="Message"
          rows={1}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) submit(e);
            if (e.key === "Escape" && busy) onStop();
          }}
        />
        <span
          className={`char-counter${near ? " char-near" : ""}${over ? " char-over" : ""}`}
          aria-live="polite"
        >
          {text.length}/{MAX_CHARS}
        </span>
      </div>
      {busy ? (
        <button type="button" className="btn btn-stop" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="btn btn-send" disabled={!text.trim() || over}>
          Send
        </button>
      )}
    </form>
  );
}
