import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./CodeBlock";

interface Props {
  content: string;
  streaming: boolean;
}

function hasOpenFence(text: string): boolean {
  let inFence = false;
  for (const line of text.split("\n")) {
    if (line.trimStart().startsWith("```")) {
      inFence = !inFence;
    }
  }
  return inFence;
}

export function MarkdownBody({ content, streaming }: Props) {
  const buffered = streaming && hasOpenFence(content);

  if (buffered) {
    const lastFence = content.lastIndexOf("```");
    const beforeFence = content.slice(0, lastFence);
    const fenceLine = content.slice(lastFence);
    return (
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
          {beforeFence}
        </ReactMarkdown>
        <div className="code-skeleton">
          <code>{fenceLine.replace(/```\w*/, "")}</code>
          <span className="code-skeleton-hint" aria-hidden="true" />
        </div>
      </div>
    );
  }

  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
