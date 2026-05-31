"""Input guardrail — reject prompt-injection / jailbreak attempts.

Heuristic and deterministic: a curated set of patterns that overwhelmingly indicate
an attempt to override the system prompt or exfiltrate it. Tuned to favor precision
(few false positives on genuine support questions) over exhaustive recall.
"""

import logging
import re

from config import get_settings
from guardrails.exceptions import GuardrailViolation

logger = logging.getLogger(__name__)

# Each pattern targets a well-known injection / jailbreak phrasing. Case-insensitive.
_INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|system)\b", re.I),
    re.compile(r"forget\s+(?:everything|all\s+(?:previous|prior)|your\s+instructions)", re.I),
    re.compile(
        r"\b(?:reveal|show|print|repeat|expose|leak)\b.{0,30}\b(?:system\s+prompt|your\s+instructions|prompt)\b",
        re.I,
    ),
    re.compile(r"\byou\s+are\s+now\b.{0,40}\b(?:DAN|developer\s+mode|unrestricted|jailbroken)\b", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bpretend\s+(?:you\s+are|to\s+be)\b.{0,40}\b(?:no\s+restrictions|unfiltered|evil)\b", re.I),
    re.compile(r"\bact\s+as\b.{0,30}\b(?:unfiltered|unrestricted|jailbroken|without\s+restrictions)\b", re.I),
    re.compile(r"\boverride\b.{0,20}\b(?:safety|guardrails|restrictions|system)\b", re.I),
    re.compile(r"\bnew\s+instructions?\s*:\s*", re.I),
    re.compile(r"<\s*/?\s*(?:system|im_start|im_end)\s*>", re.I),
)


def _injection_match(text: str) -> str | None:
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def check_input(text: str) -> None:
    """Validate user input. Raises ``GuardrailViolation`` (a ``ValueError``) on rejection.

    No-op when guardrails are disabled. Length/empty checks remain in the request
    schema; this guard focuses on adversarial intent.
    """
    settings = get_settings()
    if not settings.guardrails_enabled:
        return

    if settings.guardrails_block_injection:
        matched = _injection_match(text)
        if matched:
            logger.warning("Input guardrail blocked a likely prompt-injection attempt (pattern=%r)", matched)
            raise GuardrailViolation(
                "Your message was blocked because it resembles an attempt to override the assistant's instructions.",
                reason="prompt_injection",
            )
