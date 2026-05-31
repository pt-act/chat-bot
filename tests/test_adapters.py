"""Tests for LLM and embedding adapters."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from utils.embedding_adapter import FASTEMBED_MODELS, get_embeddings, list_supported_models
from utils.llm_adapter import OPENAI_COMPATIBLE, PROVIDER_ALIASES, get_llm


class TestLLMAdapter:
    def setup_method(self):
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
    def test_google_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="google",
            llm_model="gemini-2.0-flash",
            llm_base_url="",
            openai_api_key="",
            google_api_key="AIza-test-key",
        )
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="gemini-2.0-flash",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_google_provider_missing_key_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="google",
            llm_model="gemini-2.0-flash",
            llm_base_url="",
            openai_api_key="",
            google_api_key="",
        )
        with pytest.raises(ValueError, match="GOOGLE_API_KEY is required"):
            get_llm()

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
    def test_together_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="together",
            llm_model="meta-llama/Llama-3-70b-chat-hf",
            llm_base_url="https://api.together.xyz/v1",
            openai_api_key="sk-together-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="meta-llama/Llama-3-70b-chat-hf",
                temperature=0,
                max_tokens=1000,
                base_url="https://api.together.xyz/v1",
                api_key="sk-together-xxx",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_deepseek_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="deepseek",
            llm_model="deepseek-chat",
            llm_base_url="https://api.deepseek.com/v1",
            openai_api_key="sk-deepseek-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="deepseek-chat",
                temperature=0,
                max_tokens=1000,
                base_url="https://api.deepseek.com/v1",
                api_key="sk-deepseek-xxx",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_mistral_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="mistral",
            llm_model="mistral-large-latest",
            llm_base_url="https://api.mistral.ai/v1",
            openai_api_key="sk-mistral-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="mistral-large-latest",
                temperature=0,
                max_tokens=1000,
                base_url="https://api.mistral.ai/v1",
                api_key="sk-mistral-xxx",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_fireworks_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="fireworks",
            llm_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
            llm_base_url="https://api.fireworks.ai/inference/v1",
            openai_api_key="sk-fw-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="accounts/fireworks/models/llama-v3p1-70b-instruct",
                temperature=0,
                max_tokens=1000,
                base_url="https://api.fireworks.ai/inference/v1",
                api_key="sk-fw-xxx",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_vllm_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="vllm",
            llm_model="meta-llama/Llama-3-8B-Instruct",
            llm_base_url="http://localhost:8000/v1",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="meta-llama/Llama-3-8B-Instruct",
                temperature=0,
                max_tokens=1000,
                base_url="http://localhost:8000/v1",
                api_key="no-key-needed",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_lmstudio_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="lmstudio",
            llm_model="TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
            llm_base_url="http://localhost:1234/v1",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
                temperature=0,
                max_tokens=1000,
                base_url="http://localhost:1234/v1",
                api_key="no-key-needed",
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_llamacpp_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="llamacpp",
            llm_model="local-model",
            llm_base_url="http://localhost:8080/v1",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="local-model",
                temperature=0,
                max_tokens=1000,
                base_url="http://localhost:8080/v1",
                api_key="no-key-needed",
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


class TestLLMProviderAliases:
    def setup_method(self):
        get_llm.cache_clear()

    @patch("utils.llm_adapter.get_settings")
    def test_alias_claude_to_anthropic(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="claude",
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
    def test_alias_gpt_to_openai(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="gpt",
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
    def test_alias_chatgpt_to_openai(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="chatgpt",
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
    def test_alias_llama_to_ollama(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="llama",
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
    def test_alias_gemini_to_google(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="gemini",
            llm_model="gemini-2.0-flash",
            llm_base_url="",
            openai_api_key="",
            google_api_key="AIza-test-key",
        )
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="gemini-2.0-flash",
                temperature=0,
                max_tokens=1000,
            )
            assert result is not None

    @patch("utils.llm_adapter.get_settings")
    def test_alias_deepseek_preserved(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="deepseek",
            llm_model="deepseek-chat",
            llm_base_url="https://api.deepseek.com/v1",
            openai_api_key="sk-deepseek-xxx",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_llm()
            mock_cls.assert_called_once_with(
                model="deepseek-chat",
                temperature=0,
                max_tokens=1000,
                base_url="https://api.deepseek.com/v1",
                api_key="sk-deepseek-xxx",
            )
            assert result is not None


class TestLLMAdapterEdgeCases:
    def setup_method(self):
        get_llm.cache_clear()

    @patch("utils.llm_adapter.get_settings")
    def test_base_url_with_api_key(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openrouter",
            llm_model="anthropic/claude-3.5-sonnet",
            llm_base_url="https://openrouter.ai/api/v1",
            openai_api_key="sk-or-key",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_llm()
            _, call_kwargs = mock_cls.call_args_list[0]
            assert call_kwargs["api_key"] == "sk-or-key"

    @patch("utils.llm_adapter.get_settings")
    def test_base_url_without_api_key_uses_no_key_needed(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="ollama",
            llm_model="llama3.2",
            llm_base_url="http://localhost:11434/v1",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_llm()
            _, call_kwargs = mock_cls.call_args_list[0]
            assert call_kwargs["api_key"] == "no-key-needed"

    @patch("utils.llm_adapter.get_settings")
    def test_openai_without_base_url_no_extra_kwargs(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_base_url="",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_llm()
            _, call_kwargs = mock_cls.call_args_list[0]
            assert "base_url" not in call_kwargs
            assert "api_key" not in call_kwargs

    def test_provider_aliases_cover_expected_names(self):
        assert PROVIDER_ALIASES["claude"] == "anthropic"
        assert PROVIDER_ALIASES["gpt"] == "openai"
        assert PROVIDER_ALIASES["chatgpt"] == "openai"
        assert PROVIDER_ALIASES["llama"] == "ollama"
        assert PROVIDER_ALIASES["gemini"] == "google"

    def test_openai_compatible_set_includes_all_declared(self):
        expected = {
            "openai",
            "ollama",
            "openrouter",
            "together",
            "groq",
            "deepseek",
            "fireworks",
            "mistral",
            "vllm",
            "lmstudio",
            "llamacpp",
        }
        assert OPENAI_COMPATIBLE == expected

    @patch("utils.llm_adapter.get_settings")
    def test_case_insensitive_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_provider="OpenAI",
            llm_model="gpt-4o-mini",
            llm_base_url="",
            openai_api_key="",
        )
        with patch("langchain_openai.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_llm()
            mock_cls.assert_called_once()


class TestEmbeddingAdapter:
    def setup_method(self):
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
    def test_openai_text_embedding_3_large(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
        )
        with patch("langchain_openai.OpenAIEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model="text-embedding-3-large")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_huggingface_provider(self, mock_settings):
        # HuggingFace is an OPTIONAL provider — langchain-huggingface (and its torch
        # dependency) are intentionally not in requirements (CHANGELOG AD #12). Skip when
        # the optional package isn't installed so CI stays green without re-adding it.
        pytest.importorskip("langchain_huggingface")
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
    def test_fastembed_bge_small_en(self, mock_settings):
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
    def test_fastembed_all_minilm_l6_v2(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
        with patch("langchain_community.embeddings.fastembed.FastEmbedEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="sentence-transformers/all-MiniLM-L6-v2")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_fastembed_bge_base_en(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="BAAI/bge-base-en-v1.5",
        )
        with patch("langchain_community.embeddings.fastembed.FastEmbedEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="BAAI/bge-base-en-v1.5")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_fastembed_multilingual(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="BAAI/bge-m3",
        )
        with patch("langchain_community.embeddings.fastembed.FastEmbedEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="BAAI/bge-m3")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_fastembed_custom_model_passes_through(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="Qdrant/clip-ViT-B-32-vision",
        )
        with patch("langchain_community.embeddings.fastembed.FastEmbedEmbeddings") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = get_embeddings()
            mock_cls.assert_called_once_with(model_name="Qdrant/clip-ViT-B-32-vision")
            assert result is not None

    @patch("utils.embedding_adapter.get_settings")
    def test_fastembed_import_error_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="fastembed",
            embedding_model="BAAI/bge-small-en-v1.5",
        )
        with patch.dict(sys.modules, {"langchain_community.embeddings.fastembed": None}):
            with pytest.raises(ImportError, match="fastembed"):
                get_embeddings()

    @patch("utils.embedding_adapter.get_settings")
    def test_huggingface_import_error_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="huggingface",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
        with patch.dict(sys.modules, {"langchain_huggingface": None}):
            with pytest.raises(ImportError, match="langchain-huggingface"):
                get_embeddings()

    @patch("utils.embedding_adapter.get_settings")
    def test_unsupported_provider_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(
            embedding_provider="unsupported",
            embedding_model="fake-model",
        )
        with pytest.raises(ValueError, match="Unsupported EMBEDDING_PROVIDER"):
            get_embeddings()


class TestFastembedModelRegistry:
    def test_registry_contains_key_models(self):
        assert "BAAI/bge-small-en-v1.5" in FASTEMBED_MODELS
        assert "BAAI/bge-base-en-v1.5" in FASTEMBED_MODELS
        assert "BAAI/bge-large-en-v1.5" in FASTEMBED_MODELS
        assert "sentence-transformers/all-MiniLM-L6-v2" in FASTEMBED_MODELS
        assert "BAAI/bge-m3" in FASTEMBED_MODELS

    def test_registry_entries_have_required_fields(self):
        for model_name, info in FASTEMBED_MODELS.items():
            assert "dim" in info
            assert "description" in info
            assert isinstance(info["dim"], int)
            assert isinstance(info["description"], str)
            assert info["dim"] > 0

    def test_bge_small_dimensions(self):
        assert FASTEMBED_MODELS["BAAI/bge-small-en-v1.5"]["dim"] == 384

    def test_bge_base_dimensions(self):
        assert FASTEMBED_MODELS["BAAI/bge-base-en-v1.5"]["dim"] == 768

    def test_bge_large_dimensions(self):
        assert FASTEMBED_MODELS["BAAI/bge-large-en-v1.5"]["dim"] == 1024

    def test_minilm_dimensions(self):
        assert FASTEMBED_MODELS["sentence-transformers/all-MiniLM-L6-v2"]["dim"] == 384

    def test_bge_m3_dimensions(self):
        assert FASTEMBED_MODELS["BAAI/bge-m3"]["dim"] == 1024

    def test_bge_m3_is_multilingual(self):
        assert "multilingual" in FASTEMBED_MODELS["BAAI/bge-m3"]["description"].lower()

    def test_list_supported_models_returns_all(self):
        models = list_supported_models()
        assert len(models) == len(FASTEMBED_MODELS)
        for model_name in FASTEMBED_MODELS:
            assert model_name in models

    def test_list_supported_models_includes_metadata(self):
        models = list_supported_models()
        for model_name, info in models.items():
            assert "dim" in info
            assert "description" in info
