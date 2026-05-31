def build_answer_prompt(
    summary: str, history: str, docs: str, question: str, lang: str, chat_mode: str = "strict"
) -> str:
    context_block = docs.strip()
    has_context = bool(context_block)

    if chat_mode == "strict":
        return _build_strict_prompt(summary, history, context_block, question, lang, has_context)
    elif chat_mode == "open":
        return _build_open_prompt(summary, history, context_block, question, lang, has_context)
    elif chat_mode in ("learning", "learning_review"):
        # learning_review uses the same synthesis prompt as learning — the only difference
        # is downstream: its answer is queued for review rather than embedded immediately.
        return _build_learning_prompt(summary, history, context_block, question, lang, has_context)
    return _build_strict_prompt(summary, history, context_block, question, lang, has_context)


def _build_strict_prompt(
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool
) -> str:
    return f"""You are a helpful assistant for our company.

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
  "I don't have information about that in our knowledge base. Please contact support."
- Otherwise, answer ONLY from the Relevant Context. Do not add outside knowledge.
- Be concise (2-3 sentences max).
- Do not repeat history.
- YOU MUST respond in {lang} only. No exceptions.
  (If {lang} is European Portuguese, use the spelling and vocabulary of Portugal — pt-PT,
  never Brazilian Portuguese.)
"""


def _build_open_prompt(
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool
) -> str:
    return f"""You are a helpful assistant for our company.

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
    summary: str, history: str, context_block: str, question: str, lang: str, has_context: bool
) -> str:
    return f"""You are a helpful assistant for our company that learns from conversations.

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
