from functools import lru_cache
from logging import getLogger

from config import get_settings

logger = getLogger(__name__)

FASTEMBED_MODELS = {
    "BAAI/bge-small-en-v1.5": {
        "dim": 384,
        "description": "Small English model — fast, low memory, good for prototyping and small datasets",
    },
    "BAAI/bge-base-en-v1.5": {
        "dim": 768,
        "description": "Base English model — balanced speed/quality, recommended for most use cases",
    },
    "BAAI/bge-large-en-v1.5": {
        "dim": 1024,
        "description": "Large English model — highest quality, slower inference, best for production accuracy",
    },
    "sentence-transformers/all-MiniLM-L6-v2": {
        "dim": 384,
        "description": "General-purpose small model — fast, versatile, good for semantic search",
    },
    "sentence-transformers/all-MiniLM-L12-v2": {
        "dim": 384,
        "description": "Medium MiniLM — slightly better quality than L6, same dimensions",
    },
    "BAAI/bge-m3": {
        "dim": 1024,
        "description": "Multilingual model (100+ languages) — use for Arabic/English mixed content",
    },
    "nomic-ai/nomic-embed-text-v1.5": {
        "dim": 768,
        "description": "Nomic text model — 8192 token context, good for long documents",
    },
}


def list_supported_models():
    return dict(FASTEMBED_MODELS)


@lru_cache
def get_embeddings():
    setting = get_settings()
    provider = setting.embedding_provider.lower()
    model = setting.embedding_model

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model)

    elif provider == "fastembed":
        if model not in FASTEMBED_MODELS:
            known = ", ".join(sorted(FASTEMBED_MODELS.keys()))
            logger.warning(
                "EMBEDDING_MODEL='%s' is not in the built-in registry. "
                "It may still work if FastEmbed supports it. Known models: %s",
                model,
                known,
            )
        try:
            from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
        except ImportError as e:
            raise ImportError(
                "FastEmbed embeddings require the fastembed package. Install it with: pip install fastembed"
            ) from e

        return FastEmbedEmbeddings(model_name=model)

    elif provider == "huggingface":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as e:
            raise ImportError(
                "HuggingFace embeddings require optional dependencies. "
                "Install them with: pip install langchain-huggingface sentence-transformers transformers numpy"
            ) from e

        return HuggingFaceEmbeddings(model_name=model)

    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
