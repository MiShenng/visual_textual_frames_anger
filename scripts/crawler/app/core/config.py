from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "short-video-crawler"
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    debug: bool = False
    database_url: str = "sqlite:///./crawler.sqlite3"
    fallback_enabled: bool = False
    fallback_base_url: str | None = None
    fallback_api_key: str | None = None
    data_dir: Path = Field(default=Path("data"))
    video_store_dir: Path = Field(default=Path("3.21video_data"))
    comment_store_dir: Path = Field(default=Path("3.21comment_data"))
    playwright_state_dir: Path = Field(default=Path("playwright_states"))
    snapshot_dir: Path = Field(default=Path("data/snapshots"))
    request_jitter_min_ms: int = 300
    request_jitter_max_ms: int = 1200
    request_retry_max_attempts: int = 3
    request_retry_backoff_ms: int = 500
    request_proxy_switch_attempts: int = 3
    request_max_concurrency: int = 2
    anti_crawl_pause_seconds: int = 600
    anti_crawl_detection_enabled: bool = True
    search_state_max_pages: int = 0
    failure_threshold: int = 3
    cooldown_seconds: int = 300
    playwright_headless: bool = True
    playwright_timeout_ms: int = 30000
    playwright_scroll_delay_ms: int = 1200
    playwright_channel: str | None = None
    playwright_locale: str = "zh-CN"
    playwright_timezone_id: str | None = "Asia/Shanghai"
    playwright_user_agent: str | None = None
    snapshot_interval_seconds: int = 1800
    snapshot_dedup_enabled: bool = True
    snapshot_archive_keep_count: int = 5
    ipproxypool_base_url: str = "http://127.0.0.1:8000"
    ipproxypool_types: int = 0
    ipproxypool_protocol: int = 0
    ipproxypool_country: str | None = None
    ipproxypool_area: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_",
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_runtime_paths() -> Settings:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.video_store_dir.mkdir(parents=True, exist_ok=True)
    settings.comment_store_dir.mkdir(parents=True, exist_ok=True)
    settings.playwright_state_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    return settings
