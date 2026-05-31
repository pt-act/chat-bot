"""Single source of truth for feedback Redis keys (#3)."""

# Set of all feedback entry ids.
FEEDBACK_IDS_KEY = "feedback:ids"


def feedback_key(feedback_id: str) -> str:
    """Hash holding a single feedback entry's fields."""
    return f"feedback:{feedback_id}"
