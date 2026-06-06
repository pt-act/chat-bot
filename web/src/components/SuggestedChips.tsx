import type { Lang, Mode } from "../types";

interface Prompt {
  label: string;
  text: string;
  overrides?: { mode?: Mode; lang?: Lang };
}

interface Props {
  mode: Mode;
  lang: Lang;
  onSend: (text: string, overrides?: { mode?: Mode; lang?: Lang }) => void;
}

function getPrompts(mode: Mode, lang: Lang): Prompt[] {
  const prompts: Prompt[] = [];

  if (mode === "strict") {
    prompts.push({
      label: lang === "ar" ? "أجب من المعرفة العامة" : "Answer from general knowledge",
      text: "General knowledge",
      overrides: { mode: "open" },
    });
  }

  prompts.push({
    label: lang === "ar" ? "اشرح بالعربية" : "Explain in Arabic",
    text: "What is the return policy?",
    overrides: { lang: "ar" },
  });

  prompts.push({
    label: lang === "ar" ? "لخّص هذا" : "Summarize this",
    text: "Summarize the key points",
  });

  prompts.push({
    label: lang === "ar" ? "ما هي سياسة الإرجاع؟" : "What is the return policy?",
    text: "What is the return policy?",
  });

  return prompts;
}

export function SuggestedChips({ mode, lang, onSend }: Props) {
  const prompts = getPrompts(mode, lang);

  return (
    <div className="suggested-chips" role="list" aria-label="Suggested prompts">
      {prompts.map((p) => (
        <button
          key={p.label}
          type="button"
          className="chip chip-suggested"
          role="listitem"
          onClick={() => onSend(p.text, p.overrides)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
