interface Props {
  streaming: boolean;
  hasContent: boolean;
  error?: boolean;
  errorMessage?: string;
}

export function StreamingIndicator({ streaming, hasContent, error, errorMessage }: Props) {
  if (error) {
    return (
      <div className="stream-error" role="alert">
        <span className="stream-error-icon" aria-hidden="true">⚠</span>
        {errorMessage || "An error occurred while generating the response."}
      </div>
    );
  }

  if (streaming && !hasContent) {
    return (
      <div className="typing-indicator" aria-label="Generating response">
        <span className="typing-dot" aria-hidden="true" />
        <span className="typing-dot" aria-hidden="true" />
        <span className="typing-dot" aria-hidden="true" />
      </div>
    );
  }

  return null;
}
