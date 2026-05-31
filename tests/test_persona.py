"""Tests for configurable persona / refusal copy / domain scoping (#5).

The headline guarantee: defaults reproduce the original hard-coded prompt copy
byte-for-byte, so existing behavior and prompt assertions are unchanged.
"""

from prompts.answer import build_answer_prompt

_ARGS = dict(summary="S", history="H", docs="", question="Q", lang="English")


class TestPersonaDefaults:
    def test_strict_default_persona_line_unchanged(self):
        prompt = build_answer_prompt(chat_mode="strict", **_ARGS)
        assert prompt.startswith("You are a helpful assistant for our company.\n")
        # Default refusal copy is preserved verbatim.
        assert "in our knowledge base. Please contact support." in prompt

    def test_learning_default_persona_line_unchanged(self):
        prompt = build_answer_prompt(chat_mode="learning", **_ARGS)
        assert prompt.startswith("You are a helpful assistant for our company that learns from conversations.\n")

    def test_no_domain_clause_by_default(self):
        prompt = build_answer_prompt(chat_mode="open", **_ARGS)
        assert "You answer questions about" not in prompt


class TestPersonaOverrides:
    def test_assistant_name_and_escalation_flow_through(self):
        prompt = build_answer_prompt(
            chat_mode="strict",
            assistant_name="Acme Support",
            escalation_message="Email help@acme.com.",
            **_ARGS,
        )
        assert prompt.startswith("You are a helpful assistant for Acme Support.")
        assert "in our knowledge base. Email help@acme.com." in prompt

    def test_knowledge_domain_adds_framing(self):
        prompt = build_answer_prompt(
            chat_mode="open",
            knowledge_domain="returns & shipping policy",
            **_ARGS,
        )
        assert "You answer questions about returns & shipping policy." in prompt

    def test_empty_overrides_fall_back_to_defaults(self):
        prompt = build_answer_prompt(
            chat_mode="strict", assistant_name="", escalation_message="", knowledge_domain="", **_ARGS
        )
        assert prompt.startswith("You are a helpful assistant for our company.")
        assert "in our knowledge base. Please contact support." in prompt
