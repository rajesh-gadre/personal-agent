from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_llm_provider: str = "anthropic"
    default_llm_model: str = "claude-sonnet-4-20250514"
    sqlite_db_path: Path = Path("./data/personal_agent.db")

    # Receipt folders
    receipt_watch_folder: Path = Path("~/Receipts")
    receipt_staging_folder: Path = Path("./data/staging")
    receipt_archive_folder: Path = Path("./data/archive")
    receipt_rejected_folder: Path = Path("./data/rejected")
    receipt_watch_interval_seconds: int = 30
    receipt_watcher_mode: str = "event"  # "event" (watchdog) or "poll" (legacy)
    start_watcher_in_ui: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
