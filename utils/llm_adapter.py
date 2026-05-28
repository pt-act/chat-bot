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
}

# Providers that use OpenAI-compatible API format
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
}


@lru_cache
def get_llm():
    setting = get_settings()
    provider = PROVIDER_ALIASES.get(setting.llm_provider.lower(), setting.llm_provider.lower())
    model = setting.llm_model
    base_url = setting.llm_base_url or None

    # OpenAI-compatible providers — single code path
    if provider in OPENAI_COMPATIBLE:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model,
            "temperature": 0,
            "max_tokens": 1000,
        }

        # If base_url is set, use it (Ollama, OpenRouter, Together, etc.)
        if base_url:
            kwargs["base_url"] = base_url
            # Some providers need the API key, some don't (local Ollama)
            if setting.openai_api_key:
                kwargs["api_key"] = setting.openai_api_key
            else:
                kwargs["api_key"] = "no-key-needed"  # Local providers

        return ChatOpenAI(**kwargs)

    # Anthropic — native client
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=0,
            max_tokens=1000,
        )

    # Google Gemini — native client
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not setting.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            max_tokens=1000,
        )

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {provider}. "
            f"Supported: openai, anthropic, google, groq, ollama, "
            f"openrouter, together, deepseek, fireworks, mistral, "
            f"vllm, lmstudio, llamacpp"
        )
