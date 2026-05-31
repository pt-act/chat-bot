"""Single source of truth for learning-review Redis keys (two-phase ingest)."""

# Set of entry_ids currently awaiting review.
PENDING_IDS_KEY = "review:pending_ids"


def pending_key(entry_id: str) -> str:
    """Hash holding a single pending entry's fields."""
    return f"review:pending:{entry_id}"
