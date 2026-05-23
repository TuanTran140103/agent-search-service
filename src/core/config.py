from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # App
    app_name: str = "LM Agent Service"
    debug: bool = False
    port: int = 8000

    # ── Primary LLM (used by main agent & fallback) ──────────────────────
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: Optional[str] = None
    llm_temperature: float = 0.7
    llm_max_tokens: Optional[int] = None

    # ── Per-provider API keys & base URLs ────────────────────────────────
    # Each provider can override the primary key/url when you need
    # separate credentials for different model providers.
    anthropic_api_key: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    google_api_key: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    nvidia_base_url: Optional[str] = None

    # ── LangSmith (optional) ─────────────────────────────────────────────
    langsmith_api_key: Optional[str] = None
    langsmith_project: Optional[str] = "lm-agent-service"
    langsmith_tracing: bool = False

    # ── PostgreSQL (checkpointer) ────────────────────────────────────────
    database_uri: str = "postgresql://postgres:postgres@localhost:5432/lm_agent"

    # ── Redis ────────────────────────────────────────────────────────────
    redis_uri: str = "redis://localhost:6379/0"

    # ── Rate limit ───────────────────────────────────────────────────────
    rate_limit_per_user: int = 10
    rate_limit_global: int = 1000
    rate_limit_window: int = 60

    # ── LLM Cost Control ─────────────────────────────────────────────────
    llm_max_tokens_per_request: int = 4096
    llm_daily_budget_tokens: int = 10_000_000

    # ── Search API (external .NET service) ───────────────────────────────
    search_api_base_url: str = "http://localhost:5000/api/v1/search"

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = False
    log_service: str = "lm-agent-service"

    # ── Agent ────────────────────────────────────────────────────────────
    agent_name: str = "lm-assistant"
    agent_description: str = "LM Agent Service - AI Assistant with search capabilities"

    # ── DeepAgents ───────────────────────────────────────────────────────
    deepagent_memory_enabled: bool = False
    deepagent_memory_paths: list[str] = ["/memories/user_preferences.md"]

    # ── Supervisor (legacy — no longer used, kept for .env compat) ────────
    supervisor_model: Optional[str] = None
    supervisor_api_key: Optional[str] = None
    supervisor_base_url: Optional[str] = None

    # ── Human-in-the-loop ────────────────────────────────────────────────
    # Comma-separated tool names that require approval, e.g. "write_file,delete"
    deepagent_interrupt_on: str = ""


settings = Settings()
