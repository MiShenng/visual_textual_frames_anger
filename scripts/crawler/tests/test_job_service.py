import os
import tempfile
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.enums import AccountStatus, Platform, QueryType
from app.platforms.provider import ProviderClient
from app.services.accounts import AccountService
from app.services.jobs import JobService
from app.services.registry import AdapterRegistry
from app.storage.base import Base
from app.storage.models import Account, Comment, CrawlEvent, CrawlJob, Video, VideoHit


class FakeProvider(ProviderClient):
    def search(
        self,
        platform,
        query_type,
        query,
        time_range,
        limit,
        cursor=None,
        crawl_context=None,
    ):
        return [
            {
                "aweme_id": "job-test-v1",
                "desc": "demo video",
                "download_url": "https://example.com/job-test-v1.mp4",
                "author": {"uid": "a1", "nickname": "author-a"},
                "statistics": {"play_count": 99},
                "tags": ["tag-a"],
            }
        ], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        return [
            {
                "cid": "c1",
                "text": "一级评论",
                "digg_count": 2,
                "reply_comment_total": 1,
                "user": {"uid": "u1", "nickname": "commenter"},
            }
        ], None

    def replies(
        self,
        platform,
        platform_video_id,
        root_comment_platform_id,
        cursor=None,
        crawl_context=None,
    ):
        return [
            {
                "cid": "c2",
                "text": "二级回复",
                "digg_count": 1,
                "reply_comment_total": 0,
                "user": {"uid": "u2", "nickname": "replier"},
            }
        ], None


class RepeatingCursorProvider(ProviderClient):
    def search(
        self,
        platform,
        query_type,
        query,
        time_range,
        limit,
        cursor=None,
        crawl_context=None,
    ):
        return [
            {
                "aweme_id": "loop-video",
                "desc": "loop video",
                "download_url": "https://example.com/loop.mp4",
                "author": {"uid": "a-loop", "nickname": "author-loop"},
                "statistics": {"play_count": 1},
            }
        ], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        return [
            {
                "cid": "loop-c1",
                "text": "重复页一级评论",
                "digg_count": 1,
                "reply_comment_total": 0,
                "user": {"uid": "u-loop", "nickname": "loop-user"},
            }
        ], "same-cursor"

    def replies(
        self,
        platform,
        platform_video_id,
        root_comment_platform_id,
        cursor=None,
        crawl_context=None,
    ):
        return [], None


class FlakyReplyProvider(ProviderClient):
    def __init__(self):
        self.failed = False

    def search(
        self,
        platform,
        query_type,
        query,
        time_range,
        limit,
        cursor=None,
        crawl_context=None,
    ):
        return [], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        return [
            {
                "cid": "resume-c1",
                "text": "一级评论1",
                "digg_count": 1,
                "reply_comment_total": 1,
                "user": {"uid": "u-resume-1", "nickname": "resume-user-1"},
            },
            {
                "cid": "resume-c2",
                "text": "一级评论2",
                "digg_count": 1,
                "reply_comment_total": 1,
                "user": {"uid": "u-resume-2", "nickname": "resume-user-2"},
            },
        ], None

    def replies(
        self,
        platform,
        platform_video_id,
        root_comment_platform_id,
        cursor=None,
        crawl_context=None,
    ):
        if root_comment_platform_id == "resume-c2" and not self.failed:
            self.failed = True
            raise RuntimeError("reply page interrupted")
        return [
            {
                "cid": f"{root_comment_platform_id}-r1",
                "text": f"{root_comment_platform_id} 的二级回复",
                "digg_count": 1,
                "reply_comment_total": 0,
                "user": {"uid": f"{root_comment_platform_id}-u", "nickname": "reply-user"},
            }
        ], None


class HangingCommentProvider(ProviderClient):
    def search(
        self,
        platform,
        query_type,
        query,
        time_range,
        limit,
        cursor=None,
        crawl_context=None,
    ):
        return [], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        if platform_video_id == "hang-v1":
            time.sleep(2)
            return [], None
        return [
            {
                "cid": f"{platform_video_id}-c1",
                "text": "正常评论",
                "digg_count": 1,
                "reply_comment_total": 0,
                "user": {"uid": "ok-user", "nickname": "ok-user"},
            }
        ], None

    def replies(
        self,
        platform,
        platform_video_id,
        root_comment_platform_id,
        cursor=None,
        crawl_context=None,
    ):
        return [], None


def make_session() -> Session:
    temp_root = Path(tempfile.mkdtemp(prefix="po-paper-job-tests-"))
    os.environ["CRAWLER_VIDEO_STORE_DIR"] = str(temp_root / "videos")
    os.environ["CRAWLER_COMMENT_STORE_DIR"] = str(temp_root / "comments")
    os.environ["CRAWLER_SNAPSHOT_DIR"] = str(temp_root / "snapshots")
    get_settings.cache_clear()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_search_job_persists_videos_and_hits():
    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    job = service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range=None,
        limit=10,
        run_now=True,
    )
    assert job.status.value == "completed"
    assert db.query(Video).count() == 1
    assert db.query(VideoHit).count() == 1
    assert db.query(CrawlJob).count() == 2


def test_default_comment_video_timeout_is_ten_minutes():
    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    assert service._comment_video_timeout_seconds() == 600


def test_comments_job_persists_root_and_reply_comments():
    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range=None,
        limit=10,
        run_now=True,
    )
    job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["job-test-v1"],
        run_now=True,
    )
    comments = service.list_comments()
    assert job.status.value == "completed"
    assert len(comments) == 2
    assert {comment.level for comment in comments} == {1, 2}


def test_comments_job_skips_timed_out_video_and_continues():
    db = make_session()
    db.add(Video(platform=Platform.DOUYIN, platform_video_id="hang-v1", title="hang"))
    db.add(Video(platform=Platform.DOUYIN, platform_video_id="ok-v1", title="ok"))
    db.commit()

    service = JobService(db, AdapterRegistry(HangingCommentProvider()))
    service._comment_video_timeout_seconds = lambda: 1

    job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["hang-v1", "ok-v1"],
        force=True,
        run_now=True,
    )

    comments = service.list_comments()
    events = service.list_events(limit=20)

    assert job.status.value == "partial"
    assert len(comments) == 1
    assert comments[0].platform_comment_id == "ok-v1-c1"
    assert any(event.event_type == "comments_video_failed" for event in events)


def test_comments_job_failure_does_not_cooldown_account():
    db = make_session()
    db.add(Video(platform=Platform.DOUYIN, platform_video_id="hang-v1", title="hang"))
    db.add(
        Account(
            platform=Platform.DOUYIN,
            label="main",
            login_state_path="playwright_states/douyin_main.json",
            status=AccountStatus.ACTIVE,
        )
    )
    db.commit()

    service = JobService(db, AdapterRegistry(HangingCommentProvider()))
    service._comment_video_timeout_seconds = lambda: 1

    job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["hang-v1"],
        force=True,
        run_now=True,
    )

    account = AccountService(db).list_accounts()[0]

    assert job.status.value == "failed"
    assert account.status == AccountStatus.ACTIVE
    assert account.cooldown_until is None


def test_repeat_search_same_query_skips_duplicate_comment_crawl():
    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range=None,
        limit=10,
        run_now=True,
    )
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range=None,
        limit=10,
        run_now=True,
    )

    assert db.query(Video).count() == 1
    assert db.query(Comment).count() == 2
    assert db.query(VideoHit).count() == 2
    assert db.query(CrawlJob).count() == 3


def test_repeat_search_different_query_skips_duplicate_comment_crawl():
    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        time_range=None,
        limit=10,
        run_now=True,
    )
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="戒毒",
        time_range=None,
        limit=10,
        run_now=True,
    )

    assert db.query(Video).count() == 1
    assert db.query(Comment).count() == 2
    assert db.query(VideoHit).count() == 2
    assert db.query(CrawlJob).count() == 3


def test_comments_job_stops_when_cursor_repeats():
    db = make_session()
    service = JobService(db, AdapterRegistry(RepeatingCursorProvider()))
    service.create_search_job(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="循环评论",
        time_range=None,
        limit=10,
        run_now=False,
    )
    db.add(Video(platform=Platform.DOUYIN, platform_video_id="loop-video"))
    db.commit()

    job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["loop-video"],
        run_now=True,
    )

    events = db.query(CrawlEvent).filter(CrawlEvent.event_type == "comments_cursor_repeated").all()
    comments = db.query(Comment).all()

    assert job.status.value == "completed"
    assert len(comments) == 1
    assert len(events) == 1


def test_comments_job_can_resume_after_partial_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    db = make_session()
    provider = FlakyReplyProvider()
    service = JobService(db, AdapterRegistry(provider))
    db.add(Video(platform=Platform.DOUYIN, platform_video_id="resume-video"))
    db.commit()

    first_job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["resume-video"],
        run_now=True,
    )

    marker_path = Path(get_settings().comment_store_dir) / "douyin" / "resume-video.complete"
    assert first_job.status.value == "failed"
    assert db.query(Comment).count() == 3
    assert not marker_path.exists()

    second_job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["resume-video"],
        run_now=True,
    )

    assert second_job.status.value == "completed"
    assert db.query(Comment).count() == 4
    assert marker_path.exists()

    get_settings.cache_clear()


def test_comments_job_force_retries_completed_zero_comment_video(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    db = make_session()
    service = JobService(db, AdapterRegistry(FakeProvider()))
    video = Video(platform=Platform.DOUYIN, platform_video_id="force-video")
    db.add(video)
    db.commit()

    marker_path = service._comment_completion_marker_path(video)
    marker_path.write_text("{}", encoding="utf-8")

    normal_job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["force-video"],
        run_now=True,
    )
    assert normal_job.status.value == "completed"
    assert db.query(Comment).count() == 0

    forced_job = service.create_comments_job(
        platform=Platform.DOUYIN,
        platform_video_ids=["force-video"],
        force=True,
        run_now=True,
    )

    assert forced_job.status.value == "completed"
    assert db.query(Comment).count() == 2

    get_settings.cache_clear()
