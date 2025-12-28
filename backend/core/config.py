import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    weaviate_url: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    weaviate_api_key: Optional[str] = os.getenv("WEAVIATE_API_KEY")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
    max_concurrent_jobs_per_session: int = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))
    data_dir: str = os.getenv("DATA_DIR", "/data/sessions")
    cleanup_interval_seconds: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))
    google_api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
    convertapi_key: Optional[str] = os.getenv("CONVERTAPI_KEY")
    google_application_credentials: Optional[str] = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    cors_origins: list[str] = None
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:5173,http://localhost:80,http://localhost",
            ).split(",")
        os.makedirs(self.data_dir, exist_ok=True)


settings = Settings()
