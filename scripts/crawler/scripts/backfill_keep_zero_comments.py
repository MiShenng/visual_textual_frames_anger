from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import ensure_runtime_paths
from app.core.enums import JobStatus, JobType, Platform
from app.services.topic_curation import TopicCurationService
from app.storage.base import Base
from app.storage.models import Comment, CrawlJob, Video
from app.storage.session import SessionLocal, engine


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMENTS_JOB_TIMEOUT_SECONDS = 480


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry comment crawling for keep videos that currently have zero comments."
    )
    parser.add_argument("--platform", default="douyin", choices=[item.value for item in Platform])
    parser.add_argument("--curation-dir", default="data/curation/latest")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-passes", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    return parser.parse_args()


def load_keep_video_ids(curation_dir: Path) -> list[str]:
    keep_path = curation_dir / "keep_videos.csv"
    with keep_path.open(encoding="utf-8", newline="") as handle:
        return [row["platform_video_id"] for row in csv.DictReader(handle)]


def select_zero_comment_video_ids(platform: Platform, keep_video_ids: list[str]) -> list[str]:
    if not keep_video_ids:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(Video.platform_video_id)
            .outerjoin(Comment, Comment.video_id == Video.id)
            .where(
                Video.platform == platform,
                Video.platform_video_id.in_(keep_video_ids),
            )
            .group_by(Video.id)
            .having(func.count(Comment.id) == 0)
            .order_by(Video.created_at.asc(), Video.id.asc())
        ).all()
    return [row.platform_video_id for row in rows]


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def find_matching_comments_job(platform: Platform, batch: list[str]) -> CrawlJob | None:
    with SessionLocal() as db:
        jobs = db.execute(
            select(CrawlJob)
            .where(
                CrawlJob.platform == platform,
                CrawlJob.job_type == JobType.COMMENTS,
            )
            .order_by(CrawlJob.id.desc())
        ).scalars()
        for job in jobs:
            requested = job.requested_video_ids or {}
            if requested.get("video_ids") == batch and bool(requested.get("force")):
                return job
    return None


def mark_matching_comments_job_failed(
    platform: Platform, batch: list[str], error_summary: str
) -> CrawlJob | None:
    with SessionLocal() as db:
        jobs = db.execute(
            select(CrawlJob)
            .where(
                CrawlJob.platform == platform,
                CrawlJob.job_type == JobType.COMMENTS,
                CrawlJob.status == JobStatus.RUNNING,
            )
            .order_by(CrawlJob.id.desc())
        ).scalars()
        for job in jobs:
            requested = job.requested_video_ids or {}
            if requested.get("video_ids") == batch and bool(requested.get("force")):
                job.status = JobStatus.FAILED
                job.error_summary = error_summary
                db.add(job)
                db.commit()
                db.refresh(job)
                return job
    return None


def run_comments_batch(platform: Platform, batch: list[str]) -> CrawlJob | None:
    command = [sys.executable, "-u", "-m", "app.cli.main", "jobs", "comments", platform.value]
    for video_id in batch:
        command.extend(["--video-id", video_id])
    command.append("--force")
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=COMMENTS_JOB_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        reason = f"subprocess timed out after {COMMENTS_JOB_TIMEOUT_SECONDS}s"
        job = mark_matching_comments_job_failed(platform, batch, reason)
        if job is not None:
            return job
        return find_matching_comments_job(platform, batch)

    job = find_matching_comments_job(platform, batch)
    if job is not None:
        return job

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    raise RuntimeError(
        f"comments batch finished without job record: rc={completed.returncode}, stdout={stdout}, stderr={stderr}"
    )


def main() -> int:
    args = parse_args()
    ensure_runtime_paths()
    Base.metadata.create_all(bind=engine)

    platform = Platform(args.platform)
    curation_dir = Path(args.curation_dir)
    keep_video_ids = load_keep_video_ids(curation_dir)
    previous_remaining: int | None = None

    print(
        json.dumps(
            {
                "stage": "backfill_start",
                "platform": platform.value,
                "keep_video_total": len(keep_video_ids),
                "batch_size": args.batch_size,
                "max_passes": args.max_passes,
            },
            ensure_ascii=False,
        )
    )

    for pass_index in range(1, args.max_passes + 1):
        remaining = select_zero_comment_video_ids(platform, keep_video_ids)
        print(
            json.dumps(
                {
                    "stage": "pass_start",
                    "pass": pass_index,
                    "remaining_zero_comment_keep_videos": len(remaining),
                },
                ensure_ascii=False,
            )
        )
        if not remaining:
            break
        if previous_remaining is not None and len(remaining) >= previous_remaining:
            print(
                json.dumps(
                    {
                        "stage": "stabilized",
                        "pass": pass_index,
                        "remaining_zero_comment_keep_videos": len(remaining),
                    },
                    ensure_ascii=False,
                )
            )
            break

        batches = chunked(remaining, max(1, args.batch_size))
        for batch_index, batch in enumerate(batches, start=1):
            job = run_comments_batch(platform, batch)
            print(
                json.dumps(
                    {
                        "stage": "batch_completed",
                        "pass": pass_index,
                        "batch": batch_index,
                        "batches_total": len(batches),
                        "video_count": len(batch),
                        "job_id": job.id if job else None,
                        "job_status": job.status.value if job else "missing",
                        "error_summary": job.error_summary if job else None,
                    },
                    ensure_ascii=False,
                )
            )
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

        with SessionLocal() as db:
            TopicCurationService(db).export(curation_dir, platform=platform)

        previous_remaining = len(remaining)

    final_remaining = select_zero_comment_video_ids(platform, keep_video_ids)
    print(
        json.dumps(
            {
                "stage": "backfill_end",
                "remaining_zero_comment_keep_videos": len(final_remaining),
                "platform": platform.value,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
