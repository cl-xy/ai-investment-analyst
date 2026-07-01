from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    xai_api_key: str = ""
    news_api_key: str = ""
    alpha_vantage_api_key: str = ""
    mcp_data_dir: Path = Path.home() / ".mcp_investment"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "investment_analyst"
    scheduler_secret_token: str = ""
    scheduler_refresh_lock_seconds: int = 900

    @property
    def checkpointer_db(self) -> str:
        return str(Path("data") / "checkpointer.db")


settings = Settings()
