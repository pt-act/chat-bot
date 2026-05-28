"""Tests for LLM and embedding adapters."""

from unittest.mock import MagicMock, patch

import pytest

from utils.embedding_adapter import get_embeddings
from utils.llm_adapter import get_llm


class TestLLMAdapter:
    def setup_method(self):
        # Clear lru_cache before each test to prevent state leakage
        get_llm.cache_clear()

    @patch("utils.llm_adapter.get_settings")
    def test_openai_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_base_url="",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_anthropic_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="anthropic",
            llm_model="claude-3-haiku-20240307",
            llm_base_url="",
            openai_api_key="",
        )
        with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="claude-3-haiku-20240307",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_groq_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="groq",
            llm_model="llama-3.1-8b",
            llm_base_url="",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="llama-3.1-8b",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_ollama_via_base_url(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="ollama",
            llm_model="llama3.2",
            llm_base_url="http://localhost:11434/v1",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="llama3.2",
                temperature=0,
                max_tokens=1000,
                base_url="http://localhost:11434/v1",
                api_key="no-key-needed",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_openrouter_via_base_url(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openrouter",
            llm_model="anthropic/claude-3.5-sonnet",
            llm_base_url="https://openrouter.ai/api/v1",
            openai_api_key="sk-or-v1-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="anthropic/claude-3.5-sonnet",
                temperature=0,
                max_tokens=1000,
                base_url="https://openrouter.ai/api/v1",
                api_key="sk-or-v1-xxx",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_unsupported_provider_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="unsupported",
            llm_model="fake-model",
            llm_base_url="",
            openai_api_key="",
        )
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            get_llm()


class TestEmbeddingAdapter:
    def setup_method(self):
        # Clear lru_cache before each test to prevent state leakage
        get_embeddings.cache_clear()

    @patch("utils.embedding_adapter.get_settings")
    def test_openai_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
        with patch("langchain_openai.OpenAIEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model="text-embedding-3-small")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_huggingface_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="huggingface",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
        with patch("langchain_huggingface.HuggingFaceEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="sentence-transformers/all-MiniLM-L6-v2")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_fastembed_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="BAAI/bge-small-en-v1.5",
        )
        with patch("langchain_community.embeddings.fastembed.FastEmbedEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_unsupported_provider_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="unsupported",
            embedding_model="fake-model",
        )
        with pytest.raises(ValueError, match="Unsupported EMBEDDING_PROVIDER"):
            get_embeddings()
