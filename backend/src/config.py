from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openrouter_api_key: str = ""

    # LLM models
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    llm_model_fallback: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    llm_router_model: str = "openai/gpt-oss-20b:free"
    llm_router_model_fallback: str = "nvidia/nemotron-3-nano-30b-a3b:free"

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
