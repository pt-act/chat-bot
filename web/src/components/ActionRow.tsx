interface Props {
  isLastAssistant: boolean;
  isStreaming: boolean;
  onRegenerate: () => void;
  userText?: string;
  onEdit?: (text: string) => void;
}

export function ActionRow({ isLastAssistant, isStreaming, onRegenerate, userText, onEdit }: Props) {
  if (isStreaming) return null;

  return (
    <div className="action-row">
      {isLastAssistant && (
        <button type="button" className="action-btn" onClick={onRegenerate} title="Regenerate">
          ↻ Regenerate
        </button>
      )}
      {userText != null && onEdit && (
        <button type="button" className="action-btn" onClick={() => onEdit(userText)} title="Edit and resend">
          ✎ Edit
        </button>
      )}
    </div>
  );
}
