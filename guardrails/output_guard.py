"""Output guardrail — sanitize the model's answer before it leaves the system.

Enforces a hard length cap and, when enabled, masks PII (emails, phone numbers,
long digit sequences such as card numbers). Returns the (possibly modified) text
plus a flags dict describing what was applied, so callers can surface it in metadata.
"""

import logging
import re

from config import get_settings

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# 7+ digit runs allowing spaces/dashes/dots/parens — phone & card-like sequences.
_LONG_NUMBER = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)")

_EMAIL_MASK = "[redacted-email]"
_NUMBER_MASK = "[redacted-number]"


def _mask_pii(text: str) -> tuple[str, bool]:
    masked, n1 = _EMAIL.subn(_EMAIL_MASK, text)
    masked, n2 = _LONG_NUMBER.subn(_NUMBER_MASK, masked)
    return masked, bool(n1 or n2)


def sanitize_output(text: str) -> tuple[str, dict]:
    """Return ``(sanitized_text, flags)``.

    ``flags`` keys: ``masked_pii`` (bool), ``truncated`` (bool). No-op (returns the
    input unchanged with all-false flags) when guardrails are disabled.
    """
    flags = {"masked_pii": False, "truncated": False}
    settings = get_settings()
    if not settings.guardrails_enabled:
        return text, flags

    out = text

    if settings.guardrails_mask_pii:
        out, masked = _mask_pii(out)
        flags["masked_pii"] = masked

    cap = settings.guardrails_max_answer_chars
    if cap and len(out) > cap:
        # Trim on a word boundary where possible, then mark truncated.
        out = out[:cap].rsplit(" ", 1)[0].rstrip() + "…"
        flags["truncated"] = True
        logger.info("Output guardrail truncated answer to %d chars", cap)

    return out, flags
