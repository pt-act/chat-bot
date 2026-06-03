interface ModeChipProps {
  mode: string;
}

interface ProvenanceChipProps {
  selfIngessed: boolean;
}

export function ModeChip({ mode }: ModeChipProps) {
  return <span className="chip chip-mode">{mode}</span>;
}

export function ProvenanceChip({ selfIngessed }: ProvenanceChipProps) {
  if (!selfIngessed) return null;
  return (
    <span className="chip chip-provenance" title="AI-synthesized — not from official docs">
      AI-synthesized · saved to KB
    </span>
  );
}
