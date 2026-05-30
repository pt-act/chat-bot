import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Pydantic automatically matches ex:- OPENAI_API_KEY become openai_api_key
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Env vars override defaults, e.g. OPENAI_API_KEY in .env overrides the empty string below.
    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""  # Override for OpenAI-compatible endpoints (Ollama, OpenRouter, etc.)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""  # New: for Google Gemini
    groq_api_key: str = ""

    # Embeddings
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_ttl_seconds: int = 86400  # 24 hours

    # Vector DB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "policies"
    # Self-ingested (learning-mode) answers go in a SEPARATE collection so unverified,
    # model-synthesized content never pollutes authoritative strict/open retrieval.
    synthesized_collection: str = "synthesized_answers"

    # Retrieval
    # Minimum similarity score (0.0–1.0) a chunk must reach to be passed to the LLM.
    # Chunks below this score are discarded — if none pass, the bot replies with
    # "I don't have information about that" instead of hallucinating from weak matches.
    retrieval_score_threshold: float = 0.3

    chat_mode: str = "strict"  # strict | open | learning
    self_ingest_min_length: int = 50

    # Ingest
    max_file_size_mb: int = 50
    download_timeout_seconds: int = 30

    # App
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "text"  # "text" | "json" — JSON for log aggregators (Datadog, CloudWatch)
    cors_origins: list[str] = []

    # Security
    api_key: str = ""
    require_auth_for_ingest: bool = False
    trusted_proxies: list[str] = []
    allowed_hosts: list[str] = ["*"]

    @model_validator(mode="after")
    def check_api_keys(self):
        provider = self.llm_provider.lower()
        if provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if provider == "google" and not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")
        if provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return self

    @model_validator(mode="after")
    def check_chat_mode(self):
        mode = self.chat_mode.lower()
        if mode not in {"strict", "open", "learning"}:
            raise ValueError(f"CHAT_MODE must be 'strict', 'open', or 'learning' — got '{mode}'")
        return self

    @model_validator(mode="after")
    def check_embedding_keys(self):
        provider = self.embedding_provider.lower()
        if provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        if provider == "fastembed":
            from utils.embedding_adapter import FASTEMBED_MODELS

            if self.embedding_model not in FASTEMBED_MODELS:
                known = ", ".join(sorted(FASTEMBED_MODELS.keys()))
                logger.warning(
                    "EMBEDDING_MODEL='%s' is not in the built-in registry. "
                    "It may still work if FastEmbed supports it. Known models: %s",
                    self.embedding_model,
                    known,
                )
        return self

    @model_validator(mode="after")
    def check_cors(self):
        """Warn when permissive CORS is configured."""
        if "*" in self.cors_origins:
            logger.warning("CORS_ORIGINS contains '*'. This allows any origin to access the API.")
        return self


# What lru_cache does
# It means:
# “Create Settings object only ONCE, then reuse it forever.”
@lru_cache
def get_settings() -> Settings:
    return Settings()
