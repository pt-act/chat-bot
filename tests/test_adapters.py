"""Tests for LLM and embedding adapters."""

from unittest.mock import MagicMock, patch

import pytest

from utils.embedding_adapter import get_embeddings
from utils.llm_adapter import get_llm


class TestLLMAdapter:
    @patch("utils.llm_adapter.get_settings")
    def test_openai_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
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
        )
        with patch("langchain_groq.ChatGroq") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="llama-3.1-8b",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_unsupported_provider_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="unsupported",
            llm_model="fake-model",
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
    def test_unsupported_provider_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="unsupported",
            embedding_model="fake-model",
        )
        with pytest.raises(ValueError, match="Unsupported EMBEDDING_PROVIDER"):
            get_embeddings()
