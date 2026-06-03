from functools import lru_cache

from config import get_settings

# Provider aliases — normalize friendly names
PROVIDER_ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "chatgpt": "openai",
    "llama": "ollama",
    "gemini": "google",
    "mistral": "mistral",
    "deepseek": "deepseek",
    "cerebras": "cerebras",
}

OPENAI_COMPATIBLE = {
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
    "cerebras",
}


@lru_cache
def get_llm(temperature: float = 0, max_tokens: int = 1000):
    setting = get_settings()
    provider = PROVIDER_ALIASES.get(setting.llm_provider.lower(), setting.llm_provider.lower())
    model = setting.llm_model
    base_url = setting.llm_base_url or None

    # OpenAI-compatible providers — single code path
    if provider in OPENAI_COMPATIBLE:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        provider_keys = {
            "cerebras": getattr(setting, "cerebras_api_key", ""),
            "groq": getattr(setting, "groq_api_key", ""),
            "openrouter": setting.openai_api_key,
            "together": setting.openai_api_key,
            "deepseek": setting.openai_api_key,
            "fireworks": setting.openai_api_key,
            "mistral": setting.openai_api_key,
        }

        if base_url:
            kwargs["base_url"] = base_url
            key = provider_keys.get(provider, setting.openai_api_key)
            kwargs["api_key"] = key or "no-key-needed"
        elif provider != "openai":
            key = provider_keys.get(provider)
            if key:
                kwargs["api_key"] = key

        return ChatOpenAI(**kwargs)

    # Anthropic — native client
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Google Gemini — native client
    elif provider == "google":
        # Validate config before importing the optional provider package so a
        # missing key raises a clear ValueError instead of an ImportError.
        if not setting.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")

        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {provider}. "
            f"Supported: openai, anthropic, google, groq, cerebras, ollama, "
            f"openrouter, together, deepseek, fireworks, mistral, "
            f"vllm, lmstudio, llamacpp"
        )
