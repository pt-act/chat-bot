"""Prompt builders for the three answer modes.

This module is deliberately **pure** — it imports no config and reads no environment.
Persona/branding values (`assistant_name`, `knowledge_domain`, `escalation_message`)
are passed in by the caller (see graph.nodes.generate_answer.build_chat_prompt, which
reads them from config). Defaults reproduce the project's original hard-coded strings
so out-of-the-box behavior — and existing prompt assertions — are unchanged.
"""

# Defaults below intentionally reproduce the previous hard-coded copy byte-for-byte.
_DEFAULT_ASSISTANT_NAME = "our company"
_DEFAULT_ESCALATION = "Please contact support."


def _domain_clause(knowledge_domain: str) -> str:
    """Optional domain-framing sentence appended to the persona line (empty → nothing)."""
    kd = (knowledge_domain or "").strip()
    return f" You answer questions about {kd}." if kd else ""


def build_answer_prompt(
    summary: str,
    history: str,
    docs: str,
    question: str,
    lang: str,
    chat_mode: str = "strict",
    assistant_name: str = _DEFAULT_ASSISTANT_NAME,
    knowledge_domain: str = "",
    escalation_message: str = _DEFAULT_ESCALATION,
) -> str:
    context_block = docs.strip()
    has_context = bool(context_block)
    persona = {
        "assistant_name": assistant_name or _DEFAULT_ASSISTANT_NAME,
        "knowledge_domain": knowledge_domain or "",
        "escalation_message": escalation_message or _DEFAULT_ESCALATION,
    }

    if chat_mode == "strict":
        return _build_strict_prompt(summary, history, context_block, question, lang, has_context, persona)
    elif chat_mode == "open":
        return _build_open_prompt(summary, history, context_block, question, lang, has_context, persona)
    elif chat_mode in ("learning", "learning_review"):
        # learning_review uses the same synthesis prompt as learning — the only difference
        # is downstream: its answer is queued for review rather than embedded immediately.
        return _build_learning_prompt(summary, history, context_block, question, lang, has_context, persona)
    return _build_strict_prompt(summary, history, context_block, question, lang, has_context, persona)


def _build_strict_prompt(
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool, persona: dict
) -> str:
    return f"""You are a helpful assistant for {persona["assistant_name"]}.{_domain_clause(persona["knowledge_domain"])}

Conversation Summary:
{summary}

Recent Chat:
{history}

Relevant Context:
{context_block if has_context else "(no relevant documents found)"}

User Question:
{question}

Rules:
- If Relevant Context is "(no relevant documents found)" AND the user message is a conversational
  follow-up (e.g. "i called", "they said", "ok", "thanks", "what do you mean") — respond naturally
  based on the Recent Chat history. Ask a follow-up like "What did they tell you?" or acknowledge
  what they said. Do NOT use general knowledge about unrelated topics.
- If Relevant Context is "(no relevant documents found)" AND the user is asking about a new topic
  not covered in the conversation — reply ONLY with:
  "I don't have information about that in our knowledge base. {persona["escalation_message"]}"
- Otherwise, answer ONLY from the Relevant Context. Do not add outside knowledge.
- Be concise (2-3 sentences max).
- Do not repeat history.
- YOU MUST respond in {lang} only. No exceptions.
  (If {lang} is European Portuguese, use the spelling and vocabulary of Portugal — pt-PT,
  never Brazilian Portuguese.)
"""


def _build_open_prompt(
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool, persona: dict
) -> str:
    return f"""You are a helpful assistant for {persona["assistant_name"]}.{_domain_clause(persona["knowledge_domain"])}

Conversation Summary:
{summary}

Recent Chat:
{history}

Relevant Context:
{context_block if has_context else "(no relevant documents found — use your general knowledge)"}

User Question:
{question}

Rules:
- If Relevant Context contains useful information, prioritize it in your answer and cite it.
- If no relevant documents were found, you may use your general knowledge to answer helpfully.
- Always be honest about what comes from company documents vs. your general knowledge.
- Be concise (2-3 sentences max).
- Do not repeat history.
- YOU MUST respond in {lang} only. No exceptions.
  (If {lang} is European Portuguese, use the spelling and vocabulary of Portugal — pt-PT,
  never Brazilian Portuguese.)
"""


def _build_learning_prompt(
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool, persona: dict
) -> str:
    header = (
        f"You are a helpful assistant for {persona['assistant_name']} that learns from "
        f"conversations.{_domain_clause(persona['knowledge_domain'])}"
    )
    return f"""{header}

Conversation Summary:
{summary}

Recent Chat:
{history}

Relevant Context:
{context_block if has_context else "(no relevant documents found — synthesize an answer from your knowledge)"}

User Question:
{question}

Rules:
- If Relevant Context contains useful information, prioritize it in your answer and cite it.
- If no relevant documents were found, synthesize the best answer you can from your knowledge.
  Be thorough and informative — your answer may be saved to expand the knowledge base.
- When synthesizing (no documents available), clearly state: "Based on my knowledge..." so the
  user knows this isn't from an official source.
- Be concise but informative (2-4 sentences).
- Do not repeat history.
- YOU MUST respond in {lang} only. No exceptions.
  (If {lang} is European Portuguese, use the spelling and vocabulary of Portugal — pt-PT,
  never Brazilian Portuguese.)
"""
