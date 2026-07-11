from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VietDocAI"
    app_environment: str = "development"
    app_version: str = "0.2.0"
    docs_enabled: bool = True
    api_key: str | None = None
    health_broker_timeout_seconds: int = Field(default=3, ge=1, le=30)

    database_url: str
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    celery_broker_url: str
    celery_task_soft_time_limit: int = Field(default=300, ge=10)
    celery_task_time_limit: int = Field(default=330, ge=10)

    upload_dir: str = "/data/uploads"
    max_upload_mb: int = Field(default=20, ge=1, le=500)

    ocr_device: str = "cpu"
    ocr_cpu_threads: int = Field(default=4, ge=1, le=64)
    ocr_language: str = "vi"
    ocr_version: str = "PP-OCRv6"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
