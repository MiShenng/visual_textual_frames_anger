import json
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.enums import JobStatus, JobType, Platform, QueryType
from app.platforms.provider import ProviderClient
from app.services.jobs import JobService
from app.services.snapshots import SnapshotService
from app.services.registry import AdapterRegistry
from app.storage.base import Base
from app.storage.models import Comment, CrawlJob, Video


class TimeFilterProvider(ProviderClient):
    def search(self, platform, query_type, query, time_range, limit, cursor=None, crawl_context=None):
        return [
            {
                "aweme_id": "new-video",
                "desc": "new",
                "create_time": 1735689600,
                "author": {"uid": "a1", "nickname": "author-a"},
                "statistics": {"play_count": 99},
            },
            {
                "aweme_id": "old-video",
                "desc": "old",
                "create_time": 1704067200,
                "author": {"uid": "a2", "nickname": "author-b"},
                "statistics": {"play_count": 12},
            },
        ], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        return [
            {
                "cid": f"{platform_video_id}-c1",
                "text": "一级评论",
                "digg_count": 2,
                "reply_comment_total": 1,
                "user": {"uid": "u1", "nickname": "commenter"},
            }
        ], None

    def replies(self, platform, platform_video_id, root_comment_platform_id, cursor=None, crawl_context=None):
        return [
            {
                "cid": f"{root_comment_platform_id}-r1",
                "text": "二级回复",
                "digg_count": 1,
                "reply_comment_total": 0,
                "user": {"uid": "u2", "nickname": "replier"},
            }
        ], None


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_search_job_filters_old_videos_and_auto_crawls_comments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRAWLER_VIDEO_STORE_DIR", "3.21video_data")
    monkeypatch.setenv("CRAWLER_COMMENT_STORE_DIR", "3.21comment_data")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DIR", "data/snapshots")
    get_settings.cache_clear()
    db = make_session()
    service = JobService(db, AdapterRegistry(TimeFilterProvider()))

    job = service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range="2025-01-01:",
        limit=10,
        run_now=True,
    )

    videos = db.query(Video).all()
    comments = db.query(Comment).all()
    assert job.status.value == "completed"
    assert [video.platform_video_id for video in videos] == ["new-video"]
    assert len(comments) == 2

    get_settings.cache_clear()


def test_snapshot_export_writes_latest_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRAWLER_VIDEO_STORE_DIR", "3.21video_data")
    monkeypatch.setenv("CRAWLER_COMMENT_STORE_DIR", "3.21comment_data")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DIR", "data/snapshots")
    get_settings.cache_clear()
    db = make_session()
    service = JobService(db, AdapterRegistry(TimeFilterProvider()))
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range="2025-01-01:",
        limit=10,
        run_now=True,
    )
    latest_dir = Path("data/snapshots/latest")
    assert (latest_dir / "jobs.csv").exists()
    assert (latest_dir / "videos.csv").exists()
    assert (latest_dir / "comments.csv").exists()
    comment_path = Path("3.21comment_data/douyin/new-video.json")
    assert comment_path.exists()
    payload = json.loads(comment_path.read_text(encoding="utf-8"))
    assert payload["platform_video_id"] == "new-video"
    assert payload["comment_crawl_completed"] is True
    assert payload["comments"][0]["comment_level_label"] == "一级评论"
    assert payload["comments"][0]["replies"][0]["comment_level_label"] == "二级评论"
    assert payload["comments"][0]["replies"][0]["reply_to_comment_platform_id"] == "new-video-c1"
    assert payload["comments"][0]["replies"][0]["reply_to_comment_text"] == "一级评论"

    get_settings.cache_clear()


def test_snapshot_dedup_skips_duplicate_export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRAWLER_VIDEO_STORE_DIR", "3.21video_data")
    monkeypatch.setenv("CRAWLER_COMMENT_STORE_DIR", "3.21comment_data")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DIR", "data/snapshots")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DEDUP_ENABLED", "true")
    get_settings.cache_clear()

    db = make_session()
    service = SnapshotService(db)
    first = service.maybe_export(force=True)
    second = service.maybe_export(force=True)

    archives = [item for item in (tmp_path / "data" / "snapshots").iterdir() if item.is_dir() and item.name != "latest"]
    assert first is not None
    assert second is None
    assert len(archives) == 1

    get_settings.cache_clear()


def test_snapshot_prunes_old_archives(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRAWLER_VIDEO_STORE_DIR", "3.21video_data")
    monkeypatch.setenv("CRAWLER_COMMENT_STORE_DIR", "3.21comment_data")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DIR", "data/snapshots")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_DEDUP_ENABLED", "false")
    monkeypatch.setenv("CRAWLER_SNAPSHOT_ARCHIVE_KEEP_COUNT", "2")
    get_settings.cache_clear()

    db = make_session()
    service = SnapshotService(db)

    for idx in range(4):
        db.add(
            CrawlJob(
                job_type=JobType.SEARCH,
                platform=Platform.DOUYIN,
                status=JobStatus.PENDING,
                query=f"q-{idx}",
            )
        )
        db.commit()
        service.maybe_export(force=True)
        time.sleep(1.05)

    snapshot_dir = tmp_path / "data" / "snapshots"
    archives = sorted(
        [item.name for item in snapshot_dir.iterdir() if item.is_dir() and item.name != "latest"],
        reverse=True,
    )
    assert len(archives) == 2

    get_settings.cache_clear()
