class GuardrailViolation(ValueError):
    """Raised when an input guardrail rejects a request.

    Subclasses ``ValueError`` so the existing controller handlers (which already
    translate ``ValueError`` into an HTTP 400 / RFC 9457 problem response) surface
    it without special-casing. ``reason`` is a short machine-friendly code.
    """

    def __init__(self, message: str, reason: str = "guardrail_violation") -> None:
        super().__init__(message)
        self.reason = reason
