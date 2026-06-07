import json
import re
import signal
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Callable, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AntiCrawlDetectedError
from app.core.enums import CrawlSource, JobStatus, JobType, Platform, QueryType
from app.platforms.schemas import CommentRecord, CrawlContext, SearchRequest, VideoRecord
from app.services.accounts import AccountService
from app.services.fallback import FallbackProvider
from app.services.proxies import ProxyService
from app.services.registry import AdapterRegistry
from app.services.snapshots import SnapshotService
from app.storage.models import Comment, CrawlEvent, CrawlJob, Video, VideoHit


T = TypeVar("T")


class JobService:
    def __init__(self, db: Session, registry: AdapterRegistry):
        self.db = db
        self.registry = registry
        self.settings = get_settings()
        self.accounts = AccountService(db)
        self.proxies = ProxyService(db)
        self.fallback = FallbackProvider()
        self.snapshots = SnapshotService(db)

    def create_search_job(
        self,
        platform: Platform,
        query_type: QueryType,
        query: str,
        time_range: str | None,
        limit: int | None,
        run_now: bool = True,
    ) -> CrawlJob:
        job = CrawlJob(
            job_type=JobType.SEARCH,
            platform=platform,
            query_type=query_type,
            query=query,
            time_range=time_range,
            limit=limit,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        if run_now:
            self.run_search_job(job.id)
            self.db.refresh(job)
        return job

    def create_comments_job(
        self,
        platform: Platform,
        platform_video_ids: list[str],
        force: bool = False,
        run_now: bool = True,
    ) -> CrawlJob:
        job = CrawlJob(
            job_type=JobType.COMMENTS,
            platform=platform,
            requested_video_ids={"video_ids": platform_video_ids, "force": force},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        if run_now:
            self.run_comments_job(job.id)
            self.db.refresh(job)
        return job

    def retry_job(self, job_id: int) -> CrawlJob:
        job = self._get_job(job_id)
        job.retry_count += 1
        job.status = JobStatus.PENDING
        job.error_summary = None
        self.db.commit()
        if job.job_type == JobType.SEARCH:
            self.run_search_job(job.id)
        else:
            self.run_comments_job(job.id)
        self.db.refresh(job)
        return job

    def run_search_job(self, job_id: int) -> CrawlJob:
        job = self._get_job(job_id)
        adapter = self.registry.get(job.platform)
        account = self.accounts.acquire_account(job.platform)
        job.status = JobStatus.RUNNING
        self.db.commit()

        try:
            cursor = job.cursor
            remaining = job.limit
            persisted_count = 0
            video_ids_for_comments: list[str] = []
            request: SearchRequest | None = None
            while True:
                def _search_with_context(crawl_context: CrawlContext | None):
                    local_request = SearchRequest(
                        platform=job.platform,
                        query_type=job.query_type,
                        query=job.query or "",
                        time_range=job.time_range,
                        limit=remaining,
                        cursor=cursor,
                        context=crawl_context,
                    )
                    return adapter.search_videos(local_request), local_request

                (page_videos, cursor), request = self._execute_with_anti_crawl_pause(
                    job=job,
                    account=account,
                    operation=_search_with_context,
                    marker={
                        "phase": "search",
                        "query": job.query,
                        "cursor": cursor,
                    },
                )
                if not page_videos:
                    break
                page_videos = self._filter_videos_by_time(page_videos, job.time_range)
                persisted = [self._upsert_video(item) for item in page_videos]
                for video in persisted:
                    should_crawl_comments = self._should_crawl_comments(video)
                    self._record_hit(job, video.id)
                    if should_crawl_comments:
                        video_ids_for_comments.append(video.platform_video_id)
                persisted_count += len(persisted)
                job.cursor = cursor
                self.db.commit()
                self.snapshots.maybe_export()
                if remaining is not None:
                    remaining -= len(persisted)
                    if remaining <= 0:
                        cursor = None
                        break
                if cursor is None:
                    break
            source = CrawlSource.PRIMARY
            if persisted_count == 0 and request is not None:
                fallback_videos = self.fallback.search(request)
                if fallback_videos:
                    fallback_videos = self._filter_videos_by_time(fallback_videos, job.time_range)
                    persisted = [self._upsert_video(item) for item in fallback_videos]
                    for video in persisted:
                        should_crawl_comments = self._should_crawl_comments(video)
                        self._record_hit(job, video.id)
                        if should_crawl_comments:
                            video_ids_for_comments.append(video.platform_video_id)
                    persisted_count += len(persisted)
                    source = CrawlSource.FALLBACK_API
                    self.db.commit()
                    self.snapshots.maybe_export(force=True)
            self._crawl_comments_for_videos(job.platform, video_ids_for_comments, account)
            job.cursor = cursor
            job.status = JobStatus.COMPLETED
            self._log_event(
                job=job,
                event_type="search_completed",
                message=f"Persisted {persisted_count} videos",
                payload={"source": source.value},
            )
            if account:
                self.accounts.mark_success(account)
            self.db.commit()
            self.snapshots.maybe_export(force=True)
            return job
        except Exception as exc:
            if account:
                self.accounts.mark_failure(account)
            job.status = JobStatus.FAILED
            job.error_summary = str(exc)
            self._log_event(
                job=job,
                event_type="search_failed",
                message=str(exc),
                payload={"job_id": job.id},
                level="error",
            )
            self.db.commit()
            return job

    def run_comments_job(self, job_id: int) -> CrawlJob:
        job = self._get_job(job_id)
        adapter = self.registry.get(job.platform)
        account = self.accounts.acquire_account(job.platform)
        job.status = JobStatus.RUNNING
        self.db.commit()
        try:
            video_ids = (job.requested_video_ids or {}).get("video_ids", [])
            force = bool((job.requested_video_ids or {}).get("force"))
            videos = self.db.scalars(
                select(Video).where(
                    Video.platform == job.platform,
                    Video.platform_video_id.in_(video_ids),
                )
            ).all()
            total_comments = 0
            source = CrawlSource.PRIMARY
            failures: list[tuple[str, str]] = []
            for video in videos:
                if not force and not self._should_crawl_comments(video):
                    continue
                try:
                    with self._comment_video_timeout(video.platform_video_id):
                        video_comment_count, video_source = self._crawl_comments_for_video(
                            job=job,
                            video=video,
                            adapter=adapter,
                            account=account,
                            auto_generated=False,
                        )
                except Exception as exc:
                    failures.append((video.platform_video_id, str(exc)))
                    self._log_event(
                        job=job,
                        event_type="comments_video_failed",
                        message=str(exc),
                        payload={"video_id": video.platform_video_id},
                        level="error",
                    )
                    self.db.commit()
                    continue
                total_comments += video_comment_count
                if video_source == CrawlSource.FALLBACK_API:
                    source = CrawlSource.FALLBACK_API
                self.snapshots.maybe_export()
            if failures:
                first_video_id, first_error = failures[0]
                job.error_summary = (
                    f"{len(failures)} videos failed; first={first_video_id}: {first_error}"
                )
                job.status = (
                    JobStatus.PARTIAL if len(failures) < len(videos) else JobStatus.FAILED
                )
            else:
                job.status = JobStatus.COMPLETED
            self._log_event(
                job=job,
                event_type="comments_completed",
                message=f"Persisted {total_comments} comments",
                payload={"source": source.value, "failures": len(failures)},
            )
            if account:
                self.accounts.mark_success(account)
            self.db.commit()
            self.snapshots.maybe_export(force=True)
            return job
        except Exception as exc:
            if account:
                self.accounts.mark_failure(account)
            job.status = JobStatus.FAILED
            job.error_summary = str(exc)
            self._log_event(
                job=job,
                event_type="comments_failed",
                message=str(exc),
                payload={"job_id": job.id},
                level="error",
            )
            self.db.commit()
            return job

    def list_jobs(self) -> list[CrawlJob]:
        return list(self.db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc())))

    def get_job(self, job_id: int) -> CrawlJob:
        return self._get_job(job_id)

    def list_videos(
        self,
        platform: Platform | None = None,
        query: str | None = None,
        query_type: QueryType | None = None,
    ) -> list[Video]:
        stmt = select(Video)
        if platform:
            stmt = stmt.where(Video.platform == platform)
        if query or query_type:
            stmt = stmt.join(VideoHit, VideoHit.video_id == Video.id)
            if query:
                stmt = stmt.where(VideoHit.matched_query == query)
            if query_type:
                stmt = stmt.where(VideoHit.query_type == query_type)
            stmt = stmt.distinct()
        return list(self.db.scalars(stmt.order_by(Video.created_at.desc())))

    def list_comments(
        self, video_id: int | None = None, level: int | None = None
    ) -> list[Comment]:
        stmt = select(Comment)
        if video_id:
            stmt = stmt.where(Comment.video_id == video_id)
        if level:
            stmt = stmt.where(Comment.level == level)
        return list(self.db.scalars(stmt.order_by(Comment.created_at.desc())))

    def dashboard_stats(self) -> dict[str, int]:
        return {
            "jobs": self.db.scalar(select(func.count(CrawlJob.id))) or 0,
            "videos": self.db.scalar(select(func.count(Video.id))) or 0,
            "comments": self.db.scalar(select(func.count(Comment.id))) or 0,
        }

    def list_events(self, limit: int = 50) -> list[CrawlEvent]:
        stmt = select(CrawlEvent).order_by(CrawlEvent.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def _get_job(self, job_id: int) -> CrawlJob:
        job = self.db.get(CrawlJob, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        return job

    def _build_crawl_context(self, account, proxy) -> CrawlContext | None:
        if account is None and proxy is None:
            return None
        return CrawlContext(
            account_label=account.label if account else None,
            login_state_path=account.login_state_path if account else None,
            proxy_label=proxy.label if proxy else None,
            proxy_url=proxy.proxy_url if proxy else None,
        )

    def _call_with_rotating_proxy(
        self,
        account,
        operation: Callable[[CrawlContext | None], T],
    ) -> T:
        max_attempts = max(1, self.settings.request_proxy_switch_attempts)
        excluded: set[str] = set()
        last_error: Exception | None = None
        for _ in range(max_attempts):
            proxy = self.proxies.acquire_proxy(excluded)
            crawl_context = self._build_crawl_context(account, proxy)
            try:
                result = operation(crawl_context)
                if proxy is not None:
                    self.proxies.mark_success(proxy)
                return result
            except Exception as exc:
                last_error = exc
                if proxy is not None:
                    excluded.add(proxy.label)
                    self.proxies.mark_failure(proxy)
                else:
                    break
        if last_error is not None:
            raise last_error
        return operation(self._build_crawl_context(account, None))

    def _execute_with_anti_crawl_pause(
        self,
        job: CrawlJob,
        account,
        operation: Callable[[CrawlContext | None], T],
        marker: dict[str, str | None],
    ) -> T:
        while True:
            try:
                return self._call_with_rotating_proxy(account, operation)
            except AntiCrawlDetectedError as exc:
                wait_seconds = max(1, self.settings.anti_crawl_pause_seconds)
                self._log_event(
                    job=job,
                    event_type="anti_crawl_pause",
                    message=f"Anti-crawl detected, pause {wait_seconds}s then resume",
                    payload={
                        "path": exc.path,
                        "status_code": exc.status_code,
                        "marker": exc.marker,
                        "position": marker,
                        "wait_seconds": wait_seconds,
                    },
                    level="warning",
                )
                self.db.commit()
                time.sleep(wait_seconds)

    def _crawl_comments_for_videos(
        self,
        platform: Platform,
        platform_video_ids: list[str],
        account,
    ) -> None:
        if not platform_video_ids:
            return
        unique_ids = list(dict.fromkeys(platform_video_ids))
        job = CrawlJob(
            job_type=JobType.COMMENTS,
            platform=platform,
            requested_video_ids={"video_ids": unique_ids, "auto_generated": True},
            status=JobStatus.RUNNING,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        adapter = self.registry.get(platform)
        source = CrawlSource.PRIMARY
        total_comments = 0
        failures: list[tuple[str, str]] = []
        videos = self.db.scalars(
            select(Video).where(
                Video.platform == platform,
                Video.platform_video_id.in_(unique_ids),
            )
        ).all()
        try:
            for video in videos:
                if not self._should_crawl_comments(video):
                    continue
                try:
                    with self._comment_video_timeout(video.platform_video_id):
                        video_comment_count, video_source = self._crawl_comments_for_video(
                            job=job,
                            video=video,
                            adapter=adapter,
                            account=account,
                            auto_generated=True,
                        )
                except Exception as exc:
                    failures.append((video.platform_video_id, str(exc)))
                    self._log_event(
                        job=job,
                        event_type="auto_comments_video_failed",
                        message=str(exc),
                        payload={"video_id": video.platform_video_id},
                        level="error",
                    )
                    self.db.commit()
                    continue
                total_comments += video_comment_count
                if video_source == CrawlSource.FALLBACK_API:
                    source = CrawlSource.FALLBACK_API
                self.snapshots.maybe_export()
            if failures:
                first_video_id, first_error = failures[0]
                job.error_summary = (
                    f"{len(failures)} videos failed; first={first_video_id}: {first_error}"
                )
                job.status = (
                    JobStatus.PARTIAL if len(failures) < len(videos) else JobStatus.FAILED
                )
            else:
                job.status = JobStatus.COMPLETED
            self._log_event(
                job=job,
                event_type="auto_comments_completed",
                message=f"Persisted {total_comments} comments",
                payload={"source": source.value, "failures": len(failures)},
            )
            self.db.commit()
            self.snapshots.maybe_export(force=True)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_summary = str(exc)
            self._log_event(
                job=job,
                event_type="auto_comments_failed",
                message=str(exc),
                payload={"job_id": job.id},
                level="error",
            )
            self.db.commit()
            raise

    def _filter_videos_by_time(
        self,
        videos: list[VideoRecord],
        time_range: str | None,
    ) -> list[VideoRecord]:
        start_at, end_at = self._parse_time_range(time_range)
        if start_at is None and end_at is None:
            return videos
        filtered: list[VideoRecord] = []
        for video in videos:
            if video.published_at is None:
                filtered.append(video)
                continue
            if start_at and video.published_at < start_at:
                continue
            if end_at and video.published_at > end_at:
                continue
            filtered.append(video)
        return filtered

    def _parse_time_range(
        self,
        time_range: str | None,
    ) -> tuple[datetime | None, datetime | None]:
        if not time_range:
            return None, None
        value = time_range.strip()
        if ":" not in value:
            start_at = self._parse_datetime(value)
            return start_at, None
        raw_start, raw_end = value.split(":", 1)
        start_at = self._parse_datetime(raw_start) if raw_start.strip() else None
        end_at = self._parse_datetime(raw_end) if raw_end.strip() else None
        return start_at, end_at

    def _parse_datetime(self, value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _upsert_video(self, item: VideoRecord) -> Video:
        stmt = select(Video).where(
            Video.platform == item.platform,
            Video.platform_video_id == item.platform_video_id,
        )
        video = self.db.scalar(stmt)
        if video is None:
            video = Video(platform=item.platform, platform_video_id=item.platform_video_id)
            self.db.add(video)
        video.title = item.title
        video.description = item.description
        video.download_url = item.download_url
        video.share_url = item.share_url
        video.author_platform_id = item.author_platform_id or None
        video.author_name = item.author_name
        video.author_profile_url = item.author_profile_url
        video.author_signature = item.author_signature
        video.author_stats = item.author_stats
        video.tags = item.tags
        video.stats = item.stats
        video.published_at = item.published_at
        video.raw_json = item.raw_json
        video.updated_at = datetime.now(UTC)
        self.db.flush()
        return video

    def _record_hit(self, job: CrawlJob, video_id: int) -> None:
        if not job.query or not job.query_type:
            return
        stmt = select(VideoHit).where(
            VideoHit.job_id == job.id,
            VideoHit.video_id == video_id,
            VideoHit.matched_query == job.query,
            VideoHit.query_type == job.query_type,
        )
        existing = self.db.scalar(stmt)
        if existing is None:
            self.db.add(
                VideoHit(
                    job_id=job.id,
                    video_id=video_id,
                    matched_query=job.query,
                    query_type=job.query_type,
                )
            )
            self.db.flush()

    def _should_crawl_comments(self, video: Video) -> bool:
        return not self._is_comment_crawl_complete(video)

    def _upsert_comment(
        self,
        video_id: int,
        item: CommentRecord,
        parent_comment_id: int | None,
        source: CrawlSource,
    ) -> Comment:
        stmt = select(Comment).where(
            Comment.platform == item.platform,
            Comment.platform_comment_id == item.platform_comment_id,
        )
        comment = self.db.scalar(stmt)
        if comment is None:
            comment = Comment(
                platform=item.platform,
                platform_comment_id=item.platform_comment_id,
                video_id=video_id,
            )
            self.db.add(comment)
        comment.parent_comment_id = parent_comment_id
        comment.root_comment_platform_id = item.root_comment_platform_id
        comment.level = item.level
        comment.text = item.text
        comment.author_platform_id = item.author_platform_id
        comment.author_name = item.author_name
        comment.like_count = item.like_count
        comment.reply_count = item.reply_count
        comment.published_at = item.published_at
        comment.source = source
        comment.raw_json = item.raw_json
        comment.updated_at = datetime.now(UTC)
        self.db.flush()
        return comment

    def _log_event(
        self,
        job: CrawlJob,
        event_type: str,
        message: str,
        payload: dict | None = None,
        level: str = "info",
    ) -> None:
        self.db.add(
            CrawlEvent(
                job_id=job.id,
                platform=job.platform,
                level=level,
                event_type=event_type,
                message=message,
                payload=payload,
            )
        )
        self.db.flush()

    def _crawl_comments_for_video(
        self,
        job: CrawlJob,
        video: Video,
        adapter,
        account,
        auto_generated: bool,
    ) -> tuple[int, CrawlSource]:
        phase_prefix = "auto" if auto_generated else "manual"
        comments_cursor_event = (
            "auto_comments_cursor_repeated" if auto_generated else "comments_cursor_repeated"
        )
        video_completed_event = (
            "auto_comments_video_completed" if auto_generated else "comments_video_completed"
        )
        progress = {
            "comments": 0,
            "root_comments": 0,
            "replies": 0,
        }
        source = CrawlSource.PRIMARY
        cursor = None
        seen_comment_cursors: set[str] = set()
        saw_primary_comments = False

        while True:
            request_cursor = cursor
            page_comments, cursor = self._execute_with_anti_crawl_pause(
                job=job,
                account=account,
                operation=lambda crawl_context: adapter.fetch_comments(
                    video.platform_video_id, request_cursor, crawl_context
                ),
                marker={
                    "phase": f"{phase_prefix}_comments",
                    "video_id": video.platform_video_id,
                    "cursor": request_cursor,
                },
            )
            if page_comments:
                saw_primary_comments = True
                source = self._persist_comment_batch(
                    job=job,
                    video=video,
                    comments=page_comments,
                    source=source,
                    adapter=adapter,
                    account=account,
                    progress=progress,
                    auto_generated=auto_generated,
                )
                self._commit_comment_progress(
                    job=job,
                    video=video,
                    progress=progress,
                    phase=f"{phase_prefix}_comments",
                    cursor=cursor,
                )
            if cursor is None or not page_comments:
                break
            if cursor == request_cursor or cursor in seen_comment_cursors:
                self._log_event(
                    job=job,
                    event_type=comments_cursor_event,
                    message=f"Repeated comments cursor detected for {video.platform_video_id}",
                    payload={
                        "video_id": video.platform_video_id,
                        "cursor": cursor,
                    },
                    level="warning",
                )
                break
            seen_comment_cursors.add(cursor)

        if not saw_primary_comments:
            fallback_comments = self.fallback.comments(
                platform=video.platform,
                platform_video_id=video.platform_video_id,
            )
            if fallback_comments:
                source = self._persist_comment_batch(
                    job=job,
                    video=video,
                    comments=fallback_comments,
                    source=CrawlSource.FALLBACK_API,
                    adapter=adapter,
                    account=account,
                    progress=progress,
                    auto_generated=auto_generated,
                )
                self._commit_comment_progress(
                    job=job,
                    video=video,
                    progress=progress,
                    phase=f"{phase_prefix}_comments_fallback",
                    cursor=None,
                )

        self._mark_comment_crawl_complete(video, progress)
        self._log_event(
            job=job,
            event_type=video_completed_event,
            message=f"Completed comments for {video.platform_video_id}",
            payload={
                "video_id": video.platform_video_id,
                "comment_count": progress["comments"],
                "root_comment_count": progress["root_comments"],
                "reply_count": progress["replies"],
                "source": source.value,
            },
        )
        self.db.commit()
        return progress["comments"], source

    def _persist_comment_batch(
        self,
        job: CrawlJob,
        video: Video,
        comments: list[CommentRecord],
        source: CrawlSource,
        adapter,
        account,
        progress: dict[str, int],
        auto_generated: bool,
    ) -> CrawlSource:
        current_source = source
        for comment in comments:
            root = self._upsert_comment(video.id, comment, None, current_source)
            progress["comments"] += 1
            progress["root_comments"] += 1
            if comment.reply_count and comment.reply_count > 0:
                current_source = self._crawl_replies_for_root(
                    job=job,
                    video=video,
                    root=root,
                    adapter=adapter,
                    account=account,
                    source=current_source,
                    progress=progress,
                    auto_generated=auto_generated,
                )
        return current_source

    def _crawl_replies_for_root(
        self,
        job: CrawlJob,
        video: Video,
        root: Comment,
        adapter,
        account,
        source: CrawlSource,
        progress: dict[str, int],
        auto_generated: bool,
    ) -> CrawlSource:
        phase_prefix = "auto" if auto_generated else "manual"
        replies_cursor_event = (
            "auto_replies_cursor_repeated" if auto_generated else "replies_cursor_repeated"
        )
        current_source = source
        reply_cursor = None
        seen_reply_cursors: set[str] = set()
        saw_primary_replies = False

        while True:
            request_reply_cursor = reply_cursor
            page_replies, reply_cursor = self._execute_with_anti_crawl_pause(
                job=job,
                account=account,
                operation=lambda crawl_context: adapter.fetch_replies(
                    video.platform_video_id,
                    root.platform_comment_id,
                    request_reply_cursor,
                    crawl_context,
                ),
                marker={
                    "phase": f"{phase_prefix}_replies",
                    "video_id": video.platform_video_id,
                    "root_comment_id": root.platform_comment_id,
                    "cursor": request_reply_cursor,
                },
            )
            if page_replies:
                saw_primary_replies = True
                for reply in page_replies:
                    self._upsert_comment(video.id, reply, root.id, current_source)
                    progress["comments"] += 1
                    progress["replies"] += 1
                self._commit_comment_progress(
                    job=job,
                    video=video,
                    progress=progress,
                    phase=f"{phase_prefix}_replies",
                    cursor=reply_cursor,
                    root_comment_id=root.platform_comment_id,
                )
            if reply_cursor is None or not page_replies:
                break
            if reply_cursor == request_reply_cursor or reply_cursor in seen_reply_cursors:
                self._log_event(
                    job=job,
                    event_type=replies_cursor_event,
                    message=f"Repeated replies cursor detected for {root.platform_comment_id}",
                    payload={
                        "video_id": video.platform_video_id,
                        "root_comment_id": root.platform_comment_id,
                        "cursor": reply_cursor,
                    },
                    level="warning",
                )
                break
            seen_reply_cursors.add(reply_cursor)

        if not saw_primary_replies:
            fallback_replies = self.fallback.comments(
                platform=video.platform,
                platform_video_id=video.platform_video_id,
                root_comment_platform_id=root.platform_comment_id,
            )
            if fallback_replies:
                current_source = CrawlSource.FALLBACK_API
                for reply in fallback_replies:
                    self._upsert_comment(video.id, reply, root.id, current_source)
                    progress["comments"] += 1
                    progress["replies"] += 1
                self._commit_comment_progress(
                    job=job,
                    video=video,
                    progress=progress,
                    phase=f"{phase_prefix}_replies_fallback",
                    cursor=None,
                    root_comment_id=root.platform_comment_id,
                )
        return current_source

    def _commit_comment_progress(
        self,
        job: CrawlJob,
        video: Video,
        progress: dict[str, int],
        phase: str,
        cursor: str | None,
        root_comment_id: str | None = None,
    ) -> None:
        job.cursor = json.dumps(
            {
                "phase": phase,
                "video_id": video.platform_video_id,
                "cursor": cursor,
                "root_comment_id": root_comment_id,
                "comment_count": progress["comments"],
                "root_comment_count": progress["root_comments"],
                "reply_count": progress["replies"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        job.updated_at = datetime.now(UTC)
        self.db.commit()

    def _comment_completion_marker_path(self, video: Video):
        safe_video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video.platform_video_id)
        path = self.settings.comment_store_dir / video.platform.value / f"{safe_video_id}.complete"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _comment_video_timeout_seconds(self) -> int:
        return 600

    @contextmanager
    def _comment_video_timeout(self, platform_video_id: str):
        seconds = self._comment_video_timeout_seconds()
        if (
            seconds <= 0
            or not hasattr(signal, "SIGALRM")
            or threading.current_thread() is not threading.main_thread()
        ):
            yield
            return
        previous_handler = signal.getsignal(signal.SIGALRM)

        def _handle_timeout(_signum, _frame):
            raise TimeoutError(
                f"comment crawl timed out after {seconds}s for {platform_video_id}"
            )

        signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _is_comment_crawl_complete(self, video: Video) -> bool:
        return self._comment_completion_marker_path(video).exists()

    def _mark_comment_crawl_complete(self, video: Video, progress: dict[str, int]) -> None:
        marker_path = self._comment_completion_marker_path(video)
        marker_path.write_text(
            json.dumps(
                {
                    "platform": video.platform.value,
                    "platform_video_id": video.platform_video_id,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "comment_count": progress["comments"],
                    "root_comment_count": progress["root_comments"],
                    "reply_count": progress["replies"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
