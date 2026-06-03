const ARABIC = /[؀-ۿ]/;

const LANG_MAP: Record<string, "ar" | "pt"> = {
  Arabic: "ar",
  "European Portuguese": "pt",
  ar: "ar",
  pt: "pt",
};

export function dirFor(text: string): "rtl" | "ltr" {
  return ARABIC.test(text) ? "rtl" : "ltr";
}

export function langFor(
  metaLang: string | null | undefined,
  content: string,
): "ar" | "en" | "pt" {
  if (metaLang) {
    const mapped = LANG_MAP[metaLang];
    if (mapped) return mapped;
    if (metaLang === "en") return "en";
  }
  return ARABIC.test(content) ? "ar" : "en";
}
