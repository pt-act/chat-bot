import { useEffect, useState } from "react";
import { codeToHtml } from "shiki";

interface Props {
  code: string;
  lang: string;
}

export default function ShikiHighlighter({ code, lang }: Props) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    codeToHtml(code, {
      lang: lang || "text",
      theme: "github-dark-default",
    })
      .then((h) => {
        if (alive) setHtml(h);
      })
      .catch(() => {
        if (alive) setHtml(null);
      });
    return () => {
      alive = false;
    };
  }, [code, lang]);

  if (html) {
    return <div className="code-block-highlight" dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return (
    <pre className="code-block-pre">
      <code>{code}</code>
    </pre>
  );
}
