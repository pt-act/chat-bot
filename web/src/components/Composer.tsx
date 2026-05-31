import { useState } from "react";

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        className="composer-input"
        value={text}
        placeholder="Type a message…"
        aria-label="Message"
        rows={1}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) submit(e);
        }}
      />
      {busy ? (
        <button type="button" className="btn btn-stop" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="btn btn-send" disabled={!text.trim()}>
          Send
        </button>
      )}
    </form>
  );
}
