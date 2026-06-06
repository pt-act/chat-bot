import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Supported chat modes. `learning_review` behaves like `learning` (synthesizes answers to
# fill knowledge gaps) but queues them for human approval instead of embedding them
# immediately — see graph.nodes.self_ingest and services.review_service.
CHAT_MODES = ("strict", "open", "learning", "learning_review")
# Modes that synthesize gap-filling answers and may grow the knowledge base.
LEARNING_MODES = ("learning", "learning_review")

# Supported PDF parser overrides.
PDF_PARSER_OPTIONS = ("pypdf", "opendataloader")


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
    google_api_key: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""

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
    # Retrieval strategy for above-threshold lookups. `mmr` (default) preserves today's
    # behavior; `hybrid` fuses dense + BM25 lexical via RRF; `hybrid_rerank` adds a reranker.
    retrieval_strategy: str = "mmr"  # mmr | hybrid | hybrid_rerank

    # Context-aware query rewriting (#1) — condense follow-ups into a standalone search
    # query using the rolling summary + recent turns before retrieval. First turn skips it.
    query_rewrite_enabled: bool = True

    # Groundedness / faithfulness verification (#2) — check the answer is supported by the
    # retrieved chunks and surface meta.grounded; strict mode can refuse when unsupported.
    groundedness_enabled: bool = True
    groundedness_mode: str = "heuristic"  # heuristic (no LLM call) | llm (JSON judge)
    groundedness_min_score: float = 0.5  # fraction of answer sentences that must be supported
    strict_refuse_on_ungrounded: bool = True

    chat_mode: str = "strict"  # strict | open | learning | learning_review
    self_ingest_min_length: int = 50

    # Provider resilience (#14) — retry transient LLM/embedding failures + circuit breaker.
    provider_max_retries: int = 3
    provider_retry_base_delay: float = 0.5  # seconds; exponential backoff base
    circuit_breaker_enabled: bool = True
    cb_failure_threshold: int = 5  # consecutive failures before the circuit opens
    cb_reset_seconds: int = 30  # cool-down before a half-open trial call

    # Persona / branding (#5) — de-hardcode the assistant's identity, domain framing, and
    # refusal/escalation copy. Defaults reproduce the previous hard-coded prompt strings.
    assistant_name: str = "our company"
    knowledge_domain: str = ""  # e.g. "returns & shipping policy" — empty adds no framing
    escalation_message: str = "Please contact support."

    # Guardrails (lightweight, dependency-free; see guardrails/)
    guardrails_enabled: bool = True
    # Reject inputs that look like prompt-injection / jailbreak attempts (→ 400).
    guardrails_block_injection: bool = True
    # Mask PII (emails, phone numbers, credit-card-like digits) in model output.
    # Off by default: a support bot often legitimately returns contact emails.
    guardrails_mask_pii: bool = False
    # Hard cap on answer length (characters); 0 disables the cap.
    guardrails_max_answer_chars: int = 4000

    # Ingest
    max_file_size_mb: int = 50
    download_timeout_seconds: int = 30
    # Durable ingestion (#4). `inline` (default) keeps the FastAPI BackgroundTasks path;
    # `queue` enqueues jobs onto a Redis list consumed by `python -m ingest.worker`,
    # surviving restarts and retrying transient failures up to ingest_max_attempts.
    ingest_mode: str = "inline"  # inline | queue
    ingest_max_attempts: int = 3
    # Shared directory uploads are written to in queue mode so the worker can read them.
    ingest_incoming_dir: str = "./ingest_incoming"

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

    # --- OpenDataLoader PDF parser integration (spec: specs/opendataloader/) ---
    # ODL output format(s) — e.g. "json,markdown", "markdown", "json,markdown,tagged-pdf"
    odl_format: str = "json,markdown"
    # Reading-order algorithm passed to ODL
    odl_reading_order: str = "xycut"
    # Use native PDF structure tags when present
    odl_use_struct_tree: bool = False
    # Include header/footer elements in output
    odl_include_header_footer: bool = False
    # Hybrid mode backend (e.g. "docling-fast") — None disables hybrid
    odl_hybrid: str | None = None
    # Hybrid routing mode: "auto" (triage) or "full" (all pages to AI backend)
    odl_hybrid_mode: str = "auto"  # auto | full
    # URL of the hybrid sidecar server (default set in docker-compose)
    odl_hybrid_url: str | None = None
    # Fallback to local Java-only ODL when hybrid server is unreachable
    odl_hybrid_fallback: bool = False
    # Enable LaTeX formula extraction (requires hybrid_mode=full)
    odl_enrich_formula: bool = False
    # Enable picture/chart description (requires hybrid_mode=full)
    odl_enrich_pictures: bool = False
    # Global PDF parser fallback: if ODL fails, fall back to PyPDFLoader
    pdf_parser_fallback: bool = True
    # Explicit PDF parser override: "pypdf" | "opendataloader" | None (auto-detect)
    pdf_parser: str | None = None

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
        if provider == "cerebras" and not self.cerebras_api_key:
            raise ValueError("CEREBRAS_API_KEY is required when LLM_PROVIDER=cerebras")
        return self

    @model_validator(mode="after")
    def check_chat_mode(self):
        mode = self.chat_mode.lower()
        if mode not in set(CHAT_MODES):
            allowed = ", ".join(f"'{m}'" for m in CHAT_MODES)
            raise ValueError(f"CHAT_MODE must be one of {allowed} — got '{mode}'")
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

    @model_validator(mode="after")
    def check_pdf_parser(self):
        """Validate PDF_PARSER override value."""
        parser = self.pdf_parser
        if parser is not None and parser.lower() not in {"pypdf", "opendataloader"}:
            raise ValueError(f"PDF_PARSER must be 'pypdf' or 'opendataloader' — got '{parser}'")
        return self

    @model_validator(mode="after")
    def check_odl_hybrid_mode(self):
        """Validate ODL_HYBRID_MODE."""
        mode = self.odl_hybrid_mode.lower()
        if mode not in {"auto", "full"}:
            raise ValueError(f"ODL_HYBRID_MODE must be 'auto' or 'full' — got '{self.odl_hybrid_mode}'")
        return self

    @model_validator(mode="after")
    def check_odl_enrichment(self):
        """Enrichment flags require hybrid_mode=full."""
        if self.odl_hybrid_mode.lower() != "full":
            if self.odl_enrich_formula:
                raise ValueError("ODL_ENRICH_FORMULA=true requires ODL_HYBRID_MODE=full")
            if self.odl_enrich_pictures:
                raise ValueError("ODL_ENRICH_PICTURES=true requires ODL_HYBRID_MODE=full")
        return self


# What lru_cache does
# It means:
# “Create Settings object only ONCE, then reuse it forever.”
@lru_cache
def get_settings() -> Settings:
    return Settings()
