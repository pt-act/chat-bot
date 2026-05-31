// Arabic Unicode block — mirrors the backend's language detection.
const ARABIC = /[؀-ۿ]/;

export function dirFor(text: string): "rtl" | "ltr" {
  return ARABIC.test(text) ? "rtl" : "ltr";
}
