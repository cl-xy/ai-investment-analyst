from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openrouter_api_key: str = ""

    # LLM models
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
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
        "nvidia/nemotron-3.5-super-vl:free,"
        "minimax/minimax-m3.1-flash:free,"
        "google/gemma-4-31b-it:free,"
        "google/gemma-4-26b-a4b-it:free"
    )
    # Models whose OpenRouter endpoint accepts reasoning={"enabled": false}. A
    # rescue attempt on one of these skips the hidden thinking phase, which on the
    # free tier takes anywhere from 8s to 60s before the first JSON character and
    # was what used up whole turns. Probed on the production machine: ultra and
    # super-vl return valid JSON in ~8-10s with it off; minimax rejects the flag
    # (HTTP 400, reasoning is mandatory), so it is deliberately not listed.
    llm_reasoning_optional_models: str = (
        "nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free"
    )
    llm_router_model: str = "nvidia/nemotron-3.5-lightning:free"
    llm_router_model_fallback: str = "google/gemma-4-31b-it:free"

    @property
    def llm_reasoning_optional_set(self) -> frozenset[str]:
        return frozenset(
            m.strip() for m in self.llm_reasoning_optional_models.split(",") if m.strip()
        )

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

    # Wall-clock budget for the whole debate (bull + bear + moderator) on one
    # ticker. Must stay below the route's EXECUTION_TIMEOUT_PER_TICKER (180s) so
    # the debate node fails fast WITHIN the outer budget and its per-turn
    # degraded-partial handlers can run and be checkpointed, instead of the
    # outer timeout cancelling the node mid-call and losing everything. The
    # debate node splits this across the three turns, front-loading the bull
    # turn (a bull failure zeroes the whole ticker; bear/moderator degrade in
    # place). Set to 165s: the outer bound is 180s, so this leaves ~15s of margin
    # for cancellation unwind, validation, and checkpoint persistence. There is
    # no fixed pause between turns any more, so the whole budget goes to the
    # model calls.
    debate_ticker_budget_seconds: float = 165.0

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
