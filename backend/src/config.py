from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    groq_api_key: str = ""
    xai_api_key: str = ""  # legacy, kept for backward compat

    # External APIs
    news_api_key: str = ""
    alpha_vantage_api_key: str = ""
    alpha_vantage_daily_limit: int = 20

    # Data
    mcp_data_dir: Path = Path.home() / ".mcp_investment"
    database_url: str = "postgresql://localhost:5432/investment_analyst"

    # Legacy MongoDB (kept for reference, no longer used)
    mongodb_uri: str = ""
    mongodb_db: str = ""

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
