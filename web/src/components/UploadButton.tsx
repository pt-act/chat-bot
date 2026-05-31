import { useRef, useState } from "react";
import { uploadDocument } from "../lib/api";

interface Props {
  userId: string;
  disabled?: boolean;
}

const ACCEPT = ".pdf,.txt,.md,.markdown,.docx,.html,.htm";

/** Upload a local document (PDF/TXT/MD/DOCX/HTML) into the knowledge base (no URL required). */
export function UploadButton({ userId, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setBusy(true);
    setStatus(`Uploading ${file.name}…`);
    try {
      const r = await uploadDocument(file, userId);
      setStatus(`Queued “${r.doc_id}” for ingestion.`);
    } catch (err) {
      setStatus((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload">
      <input ref={inputRef} type="file" accept={ACCEPT} hidden onChange={onPick} />
      <button
        type="button"
        className="btn btn-upload"
        disabled={disabled || busy}
        onClick={() => inputRef.current?.click()}
        title="Upload a local document (PDF, TXT, MD, DOCX, HTML) to the knowledge base"
      >
        {busy ? "Uploading…" : "Upload doc"}
      </button>
      {status && (
        <span className="upload-status" role="status">
          {status}
        </span>
      )}
    </div>
  );
}
