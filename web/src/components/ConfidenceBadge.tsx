type Level = "high" | "medium" | "low";

interface Props {
  score: number | null | undefined;
}

function bucket(score: number): Level {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

const LABEL: Record<Level, string> = { high: "High", medium: "Medium", low: "Low" };

export function ConfidenceBadge({ score }: Props) {
  if (score == null) return null;
  const level = bucket(score);
  return (
    <span
      className={`confidence confidence-${level}`}
      title={`Relevance score: ${score.toFixed(2)}`}
    >
      {LABEL[level]}
    </span>
  );
}
