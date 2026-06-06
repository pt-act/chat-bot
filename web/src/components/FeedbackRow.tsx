import { useState } from "react";
import { submitFeedback } from "../lib/api";

interface Props {
  question: string;
  answer: string;
  correlationId?: string | null;
  disabled?: boolean;
}

export function FeedbackRow({ question, answer, correlationId, disabled }: Props) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [reason, setReason] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (disabled || submitted) {
    return (
      <div className="feedback-row">
        <span className="feedback-submitted" aria-label="Feedback submitted">
          {rating === "up" ? "👍 Thanks" : rating === "down" ? "👎 Thanks" : "✓ Feedback submitted"}
        </span>
      </div>
    );
  }

  async function handleSubmit(selected: "up" | "down") {
    setRating(selected);
    try {
      await submitFeedback({
        rating: selected,
        question,
        answer,
        correlation_id: correlationId,
        reason: selected === "down" ? reason || undefined : undefined,
      });
      setSubmitted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send feedback.");
      setRating(null);
    }
  }

  return (
    <div className="feedback-row">
      {error && <span className="feedback-error" role="alert">{error}</span>}
      <div className="feedback-buttons">
        <button
          type="button"
          className="feedback-btn feedback-up"
          onClick={() => handleSubmit("up")}
          title="Helpful"
          aria-label="Thumbs up — this answer was helpful"
        >
          👍
        </button>
        <button
          type="button"
          className="feedback-btn feedback-down"
          onClick={() => handleSubmit("down")}
          title="Not helpful"
          aria-label="Thumbs down — this answer was not helpful"
        >
          👎
        </button>
      </div>
      {rating === "down" && !submitted && (
        <div className="feedback-reason">
          <input
            type="text"
            className="feedback-reason-input"
            placeholder="What was wrong? (optional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={200}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit("down");
            }}
          />
          <button type="button" className="feedback-submit" onClick={() => handleSubmit("down")}>
            Submit
          </button>
        </div>
      )}
    </div>
  );
}
