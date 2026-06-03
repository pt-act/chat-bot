interface Props {
  question: string;
  onResend: (q: string, overrides?: Record<string, unknown>) => void;
}

export function RefusalCard({ question, onResend }: Props) {
  return (
    <div className="refusal" role="note">
      <p className="refusal-heading">Not in the knowledge base</p>
      <p className="refusal-body">
        No matching documents were found in strict mode. You can try asking with general knowledge
        enabled.
      </p>
      <button
        type="button"
        className="btn refusal-cta"
        onClick={() => onResend(question, { mode: "open" })}
      >
        Answer from general knowledge
      </button>
    </div>
  );
}
