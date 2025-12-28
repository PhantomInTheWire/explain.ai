import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379"
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: Optional[str] = None
    session_ttl_seconds: int = 3600
    max_concurrent_jobs_per_session: int = Field(default=3, alias="MAX_CONCURRENT_JOBS")
    data_dir: str = "/data/sessions"
    cleanup_interval_seconds: int = 300
    google_api_key: Optional[str] = None
    convertapi_key: Optional[str] = None
    google_application_credentials: Optional[str] = None
    api_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:80",
        "http://localhost",
    ]
    debug: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            return v.lower() == "true"
        return v

    def model_post_init(self, __context) -> None:
        try:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Directory creation may fail in read-only environments


settings = Settings()
