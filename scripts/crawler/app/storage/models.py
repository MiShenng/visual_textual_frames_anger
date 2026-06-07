from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AccountStatus,
    CrawlSource,
    JobStatus,
    JobType,
    Platform,
    ProxyStatus,
    QueryType,
)
from app.storage.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), index=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), index=True)
    query_type: Mapped[QueryType | None] = mapped_column(Enum(QueryType), nullable=True)
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    time_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_video_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Video(TimestampMixin, Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("platform", "platform_video_id", name="uq_platform_video_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), index=True)
    platform_video_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_platform_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class VideoHit(TimestampMixin, Base):
    __tablename__ = "video_hits"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "video_id", "matched_query", "query_type", name="uq_video_hit"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    matched_query: Mapped[str] = mapped_column(String(255))
    query_type: Mapped[QueryType] = mapped_column(Enum(QueryType))


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint(
            "platform", "platform_comment_id", name="uq_platform_comment_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    platform_comment_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id"), nullable=True, index=True
    )
    root_comment_platform_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text)
    author_platform_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[CrawlSource] = mapped_column(
        Enum(CrawlSource), default=CrawlSource.PRIMARY
    )
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), index=True)
    label: Mapped[str] = mapped_column(String(255), unique=True)
    login_state_path: Mapped[str] = mapped_column(Text)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus), default=AccountStatus.ACTIVE, index=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProxyEndpoint(TimestampMixin, Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(255), unique=True)
    proxy_url: Mapped[str] = mapped_column(Text)
    status: Mapped[ProxyStatus] = mapped_column(
        Enum(ProxyStatus), default=ProxyStatus.ACTIVE, index=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlEvent(TimestampMixin, Base):
    __tablename__ = "crawl_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"), nullable=True)
    platform: Mapped[Platform | None] = mapped_column(Enum(Platform), nullable=True)
    level: Mapped[str] = mapped_column(String(32), default="info")
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
