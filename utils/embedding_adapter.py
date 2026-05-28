from functools import lru_cache

from config import get_settings


@lru_cache
def get_embeddings():
    setting = get_settings()
    provider = setting.embedding_provider.lower()
    model = setting.embedding_model

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model)

    elif provider == "fastembed":
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
