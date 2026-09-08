"""
backend/config.py
─────────────────
Loads all configuration from the .env file using pydantic-settings.
Never hard-code secrets — always read from environment variables.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenAI ──────────────────────────────────────────────
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")

    # ── MySQL ────────────────────────────────────────────────
    mysql_host: str = Field("localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(3306, alias="MYSQL_PORT")
    mysql_user: str = Field("root", alias="MYSQL_USER")
    mysql_password: str = Field(..., alias="MYSQL_PASSWORD")
    mysql_database: str = Field("codeloom_leads", alias="MYSQL_DATABASE")

    # ── FastAPI ──────────────────────────────────────────────
    backend_host: str = Field("127.0.0.1", alias="BACKEND_HOST")
    backend_port: int = Field(8000, alias="BACKEND_PORT")

    # ── CSV Export ───────────────────────────────────────────
    csv_export_dir: str = Field("data", alias="CSV_EXPORT_DIR")

    # ── Playwright ───────────────────────────────────────────
    automation_headless: bool = Field(False, alias="AUTOMATION_HEADLESS")
    automation_slow_mo: int = Field(50, alias="AUTOMATION_SLOW_MO")


# Single shared instance imported throughout the app
settings = Settings()
