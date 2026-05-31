import type { Lang, Mode } from "../types";

const MODES: { value: Mode; label: string }[] = [
  { value: "strict", label: "strict" },
  { value: "open", label: "open" },
  { value: "learning", label: "learning" },
  { value: "learning_review", label: "learning (review)" },
];
const LANGS: { value: Lang; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "en", label: "EN" },
  { value: "ar", label: "ع" },
  { value: "pt", label: "PT" },
];

interface Props {
  mode: Mode;
  lang: Lang;
  disabled: boolean;
  onMode: (m: Mode) => void;
  onLang: (l: Lang) => void;
}

export function Controls({ mode, lang, disabled, onMode, onLang }: Props) {
  return (
    <div className="controls">
      <label className="control">
        <span className="control-label">Mode</span>
        <select
          value={mode}
          disabled={disabled}
          onChange={(e) => onMode(e.target.value as Mode)}
          aria-label="Chat mode"
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        <span className="control-label">Lang</span>
        <select
          value={lang}
          disabled={disabled}
          onChange={(e) => onLang(e.target.value as Lang)}
          aria-label="Response language"
        >
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
