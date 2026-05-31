def build_verify_prompt(answer: str, docs: str) -> str:
    """Prompt an LLM judge to decide whether ``answer`` is supported by ``docs`` (#2).

    The model must return ONLY a JSON object so the verdict can be parsed deterministically:
    ``{"grounded": true|false, "unsupported_claims": ["..."]}``.
    """
    return f"""You are a strict faithfulness judge for a retrieval-augmented assistant.
Decide whether EVERY factual claim in the Answer is supported by the Context.
A claim is unsupported if it is not stated in, or cannot be directly inferred from, the Context.

Return ONLY a JSON object, no prose:
{{"grounded": true|false, "unsupported_claims": ["<claim>", ...]}}

Context:
{docs}

Answer:
{answer}

JSON:"""
