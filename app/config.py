from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "VideoStream"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    token_expiry_minutes: int = 120

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'videostream.db').as_posix()}"
    media_root: Path = BASE_DIR / "data" / "media"

    storage_backend: str = "local"
    azure_connection_string: str = ""
    azure_container: str = "videos"
    s3_bucket: str = ""
    s3_region: str = "eu-west-1"
    ffmpeg_path: str = ""
    max_upload_mb: int = 200
    allowed_video_types: list[str] = ["video/mp4", "video/webm", "video/ogg", "video/quicktime"]

    dashboard_page_size: int = 12
    cache_ttl_seconds: int = 30

    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
