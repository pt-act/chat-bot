"""Lightweight, dependency-free guardrails for the chat pipeline.

Two layers, both toggleable via `config.Settings`:

- **Input guard** (`input_guard.check_input`) — runs before the graph. Rejects
  prompt-injection / jailbreak attempts so untrusted user text cannot subvert the
  system prompt. Raises `GuardrailViolation` (a `ValueError`, so existing controller
  handlers map it to HTTP 400 / problem+json).
- **Output guard** (`output_guard.sanitize_output`) — runs on the model's answer.
  Enforces a length cap and (optionally) masks PII before the answer is returned,
  stored in memory, or queued for review.

Deterministic and offline by design — no model calls — so the test suite stays
hermetic and the guards add negligible latency.
"""

from guardrails.exceptions import GuardrailViolation
from guardrails.input_guard import check_input
from guardrails.output_guard import sanitize_output

__all__ = ["GuardrailViolation", "check_input", "sanitize_output"]
