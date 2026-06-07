from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import Platform, QueryType


@dataclass(slots=True)
class VideoRecord:
    platform: Platform
    platform_video_id: str
    title: str | None = None
    description: str | None = None
    download_url: str | None = None
    share_url: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    author_profile_url: str | None = None
    author_signature: str | None = None
    author_stats: dict | None = None
    tags: list[str] = field(default_factory=list)
    stats: dict | None = None
    published_at: datetime | None = None
    raw_json: dict | None = None


@dataclass(slots=True)
class CommentRecord:
    platform: Platform
    platform_comment_id: str
    text: str
    level: int
    root_comment_platform_id: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    like_count: int | None = None
    reply_count: int | None = None
    published_at: datetime | None = None
    raw_json: dict | None = None


@dataclass(slots=True)
class CrawlContext:
    account_label: str | None = None
    login_state_path: str | None = None
    proxy_label: str | None = None
    proxy_url: str | None = None


@dataclass(slots=True)
class SearchRequest:
    platform: Platform
    query_type: QueryType
    query: str
    time_range: str | None = None
    limit: int | None = None
    cursor: str | None = None
    context: CrawlContext | None = None
