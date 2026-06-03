import { lazy, Suspense, useState } from "react";
import type { ReactNode } from "react";

const ShikiHighlighter = lazy(() => import("./ShikiHighlighter"));

interface Props {
  className?: string;
  children?: ReactNode;
  inline?: boolean;
}

function isInline(code: string, className?: string): boolean {
  if (className) return false;
  return !code.includes("\n");
}

export function CodeBlock({ className, children, inline }: Props) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");
  const lang = className?.replace(/^language-/, "") || "";
  const isCode = !isInline(code, className) && !inline;

  if (!isCode) {
    return <code className={className}>{children}</code>;
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="code-block">
      <div className="code-block-header">
        {lang && <span className="code-block-lang">{lang}</span>}
        <button type="button" className="code-block-copy" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <Suspense
        fallback={
          <pre className="code-block-pre">
            <code>{code}</code>
          </pre>
        }
      >
        <ShikiHighlighter code={code} lang={lang} />
      </Suspense>
    </div>
  );
}
