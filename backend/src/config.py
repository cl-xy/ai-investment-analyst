from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openrouter_api_key: str = ""

    # LLM models
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    # Keep fallbacks on a different upstream provider so an Nvidia worker
    # exhaustion does not also take down the recovery path.
    llm_model_fallback: str = "google/gemma-4-31b-it:free"
    # Ordered recovery chain tried after the primary, across distinct upstream
    # providers. The free-tier 429s are limit_source=upstream_provider_shared_pool,
    # so a single same-provider fallback is not enough: when one provider's pool
    # is saturated, we need to route to a genuinely different provider. All models
    # here support response_format=json_object (required for the debate's JSON mode).
    # Comma-separated; override via LLM_FALLBACK_MODELS env var.
    llm_fallback_models: str = (
        "google/gemma-4-31b-it:free,"
        "qwen/qwen3.8-27b:free,"
        "dots-studio/dots-3-note-preview:free,"
        "google/gemma-4-26b-a4b-it:free"
    )
    llm_router_model: str = "nvidia/nemotron-3.5-lightning:free"
    llm_router_model_fallback: str = "google/gemma-4-31b-it:free"

    @property
    def llm_fallback_chain(self) -> list[str]:
        """Ordered, de-duplicated list of fallback model IDs to try after primary."""
        seen: dict[str, None] = {}
        for mid in self.llm_fallback_models.split(","):
            mid = mid.strip()
            if mid:
                seen.setdefault(mid, None)
        return list(seen)

    # Hard wall-clock ceiling on a single LLM attempt. request_timeout on
    # ChatOpenAI is only an httpx inter-chunk read timeout, so a trickling
    # free-tier stream (a token or keepalive every <120s) never trips it and
    # the call hangs until the outer run budget is exhausted. This bounds each
    # attempt in real time so a stall fails fast and the fallback chain runs.
    # Set below a healthy free-tier completion (observed ~44s for a debate turn)
    # so a genuinely working model still finishes, but a stalled primary is
    # abandoned quickly: with a 3-turn debate and a multi-model chain, every
    # second spent waiting on a dead primary is multiplied across turns.
    llm_attempt_timeout_seconds: float = 45.0

    # External APIs
    news_api_key: str = ""
    alpha_vantage_api_key: str = ""
    alpha_vantage_daily_limit: int = 20

    # Data
    mcp_data_dir: Path = Path.home() / ".mcp_investment"
    database_url: str = "postgresql://localhost:5432/investment_analyst"

    # Auth & rate limiting
    demo_password: str = ""
    rate_limit: str = "10/minute"

    # Scheduler
    scheduler_secret_token: str = ""
    scheduler_refresh_lock_seconds: int = 900

    # Telegram bot (Reasoning-Aware Signal Alerts)
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Server
    port: int = 8000
    frontend_url: str = "http://localhost:5173"

    @property
    def checkpointer_db(self) -> str:
        return str(Path("data") / "checkpointer.db")

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://ai-investment-analyst-iota.vercel.app",
        ]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins


settings = Settings()
