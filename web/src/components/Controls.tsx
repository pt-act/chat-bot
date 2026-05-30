import type { Lang, Mode } from "../types";

const MODES: Mode[] = ["strict", "open", "learning"];
const LANGS: { value: Lang; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "en", label: "EN" },
  { value: "ar", label: "ع" },
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
            <option key={m} value={m}>
              {m}
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
