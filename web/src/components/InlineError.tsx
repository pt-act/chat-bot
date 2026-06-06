interface Props {
  status: number;
  title?: string | null;
  detail?: string | null;
  correlationId?: string | null;
}

export function InlineError({ status, title, detail, correlationId }: Props) {
  const friendlyMessages: Record<number, string> = {
    400: "The request wasn't quite right. Please try rephrasing your question.",
    429: "Too many messages. Please wait a moment before sending another.",
    500: "Something went wrong on our side. We're looking into it.",
    502: "The server is temporarily unreachable. Please try again in a moment.",
    503: "The service is currently overloaded. Please try again shortly.",
  };

  const message = friendlyMessages[status] ?? title ?? "An unexpected error occurred.";

  return (
    <div className="inline-error" role="alert">
      <span className="inline-error-icon" aria-hidden="true">⚠</span>
      <div className="inline-error-body">
        <p className="inline-error-message">{message}</p>
        {detail && detail !== message && (
          <p className="inline-error-detail">{detail}</p>
        )}
        {correlationId && (
          <button
            type="button"
            className="inline-error-report"
            onClick={(e) => {
              const btn = e.currentTarget;
              navigator.clipboard.writeText(correlationId).then(() => {
                btn.textContent = "Copied!";
                setTimeout(() => {
                  btn.textContent = `Report issue (${correlationId.slice(0, 8)}…)`;
                }, 2000);
              });
            }}
          >
            Report issue ({correlationId.slice(0, 8)}…)
          </button>
        )}
      </div>
    </div>
  );
}
