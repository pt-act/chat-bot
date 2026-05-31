def build_condense_prompt(summary: str, history: str, question: str) -> str:
    """Prompt the LLM to rewrite a follow-up into a standalone search query (#1).

    The model must output ONLY the rewritten query (no preamble) so the result can be
    embedded directly for retrieval. Generation still uses the original question.
    """
    return f"""Rewrite the user's latest question as a standalone search query using the conversation.
Resolve pronouns and ellipsis ("what about damaged ones?" → "return policy for damaged items").
Output ONLY the rewritten query on a single line — no quotes, no preamble, no explanation.

Conversation Summary:
{summary}

Recent Chat:
{history}

Latest Question:
{question}

Standalone search query:"""
