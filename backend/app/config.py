from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "BIFlow"
    log_level: str = "INFO"
    log_json: bool = False

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://biflow:change-me-in-production@localhost:5432/biflow"
    analytics_database_url: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "biflow"

    data_dir: Path = Path("./data")
    max_upload_mb: int = 200
    profile_sample_rows: int = 50_000
    llm_sample_rows: int = 20

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_enabled: bool = True
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    groq_api_key: str = ""
    groq_api_base: str = "https://api.groq.com/openai/v1"

    secret_key: str = "replace-with-a-long-random-string"
    upload_allowed_extensions: str = "csv,parquet,xlsx,xls"

    pipeline_max_retries: int = 2
    pipeline_step_timeout_seconds: int = 900
    max_profile_columns: int = 250
    duckdb_memory_limit: str = "2GB"

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {ext.strip().lower() for ext in self.upload_allowed_extensions.split(",") if ext.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def llm_configured(self) -> bool:
        if not self.llm_enabled:
            return False
        provider = self.llm_provider.lower()
        if provider == "groq":
            return bool(self.groq_api_key)
        if provider in {"openai", "local"}:
            return bool(self.openai_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    return settings
