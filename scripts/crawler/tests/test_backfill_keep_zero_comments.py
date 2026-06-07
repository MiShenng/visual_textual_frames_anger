from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import JobStatus, JobType, Platform
from app.storage.base import Base
from app.storage.models import CrawlJob
from scripts import backfill_keep_zero_comments as backfill


def make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_find_matching_comments_job_prefers_force_batch(monkeypatch):
    session_factory = make_session_factory()
    monkeypatch.setattr(backfill, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(
            CrawlJob(
                job_type=JobType.COMMENTS,
                platform=Platform.DOUYIN,
                status=JobStatus.COMPLETED,
                requested_video_ids={"video_ids": ["v1"], "force": True},
            )
        )
        db.add(
            CrawlJob(
                job_type=JobType.COMMENTS,
                platform=Platform.DOUYIN,
                status=JobStatus.RUNNING,
                requested_video_ids={"video_ids": ["v2"], "force": True},
            )
        )
        db.commit()

    job = backfill.find_matching_comments_job(Platform.DOUYIN, ["v2"])

    assert job is not None
    assert job.requested_video_ids == {"video_ids": ["v2"], "force": True}


def test_mark_matching_comments_job_failed_updates_running_job(monkeypatch):
    session_factory = make_session_factory()
    monkeypatch.setattr(backfill, "SessionLocal", session_factory)

    with session_factory() as db:
        db.add(
            CrawlJob(
                job_type=JobType.COMMENTS,
                platform=Platform.DOUYIN,
                status=JobStatus.RUNNING,
                requested_video_ids={"video_ids": ["v1"], "force": True},
            )
        )
        db.commit()

    job = backfill.mark_matching_comments_job_failed(
        Platform.DOUYIN, ["v1"], "subprocess timed out after 480s"
    )

    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.error_summary == "subprocess timed out after 480s"
