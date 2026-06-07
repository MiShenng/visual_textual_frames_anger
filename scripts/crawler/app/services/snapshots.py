import csv
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.serializers import comment_to_dict, job_to_dict, video_to_dict
from app.core.config import ensure_runtime_paths
from app.storage.models import Comment, CrawlJob, Video


class SnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = ensure_runtime_paths()
        self.last_export_at: datetime | None = None
        self.last_signature: dict | None = None

    def maybe_export(self, force: bool = False) -> Path | None:
        now = datetime.now(UTC)
        if not force and self.last_export_at is not None:
            elapsed = (now - self.last_export_at).total_seconds()
            if elapsed < self.settings.snapshot_interval_seconds:
                return None
        signature = self._build_signature()
        if self.settings.snapshot_dedup_enabled and self._is_duplicate_signature(signature):
            self.last_export_at = now
            return None
        stamp = now.strftime("%Y%m%d_%H%M%S")
        latest_dir = self.settings.snapshot_dir / "latest"
        archive_dir = self.settings.snapshot_dir / stamp
        latest_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        jobs = list(self.db.query(CrawlJob).all())
        videos = list(self.db.query(Video).order_by(Video.created_at.asc(), Video.id.asc()).all())
        comments = list(
            self.db.query(Comment)
            .order_by(Comment.video_id.asc(), Comment.level.asc(), Comment.created_at.asc(), Comment.id.asc())
            .all()
        )
        jobs_rows = [job_to_dict(item) for item in jobs]
        videos_rows = [video_to_dict(item) for item in videos]
        comments_rows = [comment_to_dict(item) for item in comments]
        video_comment_map_rows = self._write_comment_exports(videos, comments)

        self._write_csv(latest_dir / "jobs.csv", jobs_rows)
        self._write_csv(latest_dir / "videos.csv", videos_rows)
        self._write_csv(latest_dir / "comments.csv", comments_rows)
        self._write_csv(latest_dir / "video_comment_map.csv", video_comment_map_rows)
        self._write_csv(archive_dir / "jobs.csv", jobs_rows)
        self._write_csv(archive_dir / "videos.csv", videos_rows)
        self._write_csv(archive_dir / "comments.csv", comments_rows)
        self._write_csv(archive_dir / "video_comment_map.csv", video_comment_map_rows)

        self._write_signature(latest_dir / ".signature.json", signature)
        self.last_signature = signature
        self._prune_archives()
        self.last_export_at = now
        return archive_dir

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_comment_exports(
        self,
        videos: list[Video],
        comments: list[Comment],
    ) -> list[dict]:
        comments_by_video: dict[int, list[Comment]] = {}
        for comment in comments:
            comments_by_video.setdefault(comment.video_id, []).append(comment)

        rows: list[dict] = []
        for video in videos:
            video_comments = comments_by_video.get(video.id, [])
            comment_file_path = self._comment_file_path(video)
            comment_completion_marker_path = self._comment_completion_marker_path(video)
            comment_file_path.parent.mkdir(parents=True, exist_ok=True)
            comment_file_path.write_text(
                json.dumps(
                    self._build_comment_payload(video, video_comments, comment_file_path),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            video_file_path = self._video_file_path(video)
            rows.append(
                {
                    "video_id": video.id,
                    "platform": video.platform.value,
                    "platform_video_id": video.platform_video_id,
                    "video_file_path": str(video_file_path),
                    "video_file_exists": video_file_path.exists(),
                    "comment_file_path": str(comment_file_path),
                    "comment_file_exists": comment_file_path.exists(),
                    "comment_completion_marker_path": str(comment_completion_marker_path),
                    "comment_crawl_completed": comment_completion_marker_path.exists(),
                    "comment_count": len(video_comments),
                    "root_comment_count": len([item for item in video_comments if item.level == 1]),
                    "reply_count": len([item for item in video_comments if item.level == 2]),
                }
            )
        self._write_csv(self.settings.comment_store_dir / "video_comment_map.csv", rows)
        return rows

    def _build_comment_payload(
        self,
        video: Video,
        comments: list[Comment],
        comment_file_path: Path,
    ) -> dict:
        roots: list[dict] = []
        root_entries: dict[str, dict] = {}

        for comment in comments:
            if comment.level != 1:
                continue
            entry = self._comment_export_row(comment)
            entry["replies"] = []
            roots.append(entry)
            root_entries[comment.platform_comment_id] = entry

        orphan_replies: list[dict] = []
        for comment in comments:
            if comment.level != 2:
                continue
            entry = self._comment_export_row(comment)
            entry["reply_to_comment_platform_id"] = comment.root_comment_platform_id
            root = root_entries.get(comment.root_comment_platform_id or "")
            entry["reply_to_comment_text"] = root["text"] if root else None
            if root is None:
                orphan_replies.append(entry)
                continue
            root["replies"].append(entry)

        video_file_path = self._video_file_path(video)
        comment_completion_marker_path = self._comment_completion_marker_path(video)
        return {
            "video_id": video.id,
            "platform": video.platform.value,
            "platform_video_id": video.platform_video_id,
            "title": video.title,
            "description": video.description,
            "video_file_path": str(video_file_path),
            "video_file_exists": video_file_path.exists(),
            "comment_file_path": str(comment_file_path),
            "comment_completion_marker_path": str(comment_completion_marker_path),
            "comment_crawl_completed": comment_completion_marker_path.exists(),
            "comment_count": len(comments),
            "root_comment_count": len(roots),
            "reply_count": len([item for item in comments if item.level == 2]),
            "comments": roots,
            "orphan_replies": orphan_replies,
        }

    def _comment_export_row(self, comment: Comment) -> dict:
        row = comment_to_dict(comment)
        row["comment_level_label"] = row.pop("level_label")
        return row

    def _video_file_path(self, video: Video) -> Path:
        safe_video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video.platform_video_id)
        return self.settings.video_store_dir / video.platform.value / f"{safe_video_id}.mp4"

    def _comment_file_path(self, video: Video) -> Path:
        safe_video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video.platform_video_id)
        return self.settings.comment_store_dir / video.platform.value / f"{safe_video_id}.json"

    def _comment_completion_marker_path(self, video: Video) -> Path:
        safe_video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video.platform_video_id)
        return self.settings.comment_store_dir / video.platform.value / f"{safe_video_id}.complete"

    def _build_signature(self) -> dict:
        def _max_iso(value) -> str | None:
            if value is None:
                return None
            return value.isoformat()

        return {
            "jobs_count": int(self.db.query(func.count(CrawlJob.id)).scalar() or 0),
            "videos_count": int(self.db.query(func.count(Video.id)).scalar() or 0),
            "comments_count": int(self.db.query(func.count(Comment.id)).scalar() or 0),
            "jobs_updated_max": _max_iso(self.db.query(func.max(CrawlJob.updated_at)).scalar()),
            "videos_updated_max": _max_iso(self.db.query(func.max(Video.updated_at)).scalar()),
            "comments_updated_max": _max_iso(self.db.query(func.max(Comment.updated_at)).scalar()),
        }

    def _is_duplicate_signature(self, signature: dict) -> bool:
        if self.last_signature == signature:
            return True

        signature_path = self.settings.snapshot_dir / "latest" / ".signature.json"
        if signature_path.exists():
            try:
                previous = json.loads(signature_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous = None
            if previous == signature:
                self.last_signature = signature
                return True
        return False

    def _write_signature(self, path: Path, signature: dict) -> None:
        path.write_text(
            json.dumps(signature, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _prune_archives(self) -> None:
        keep = max(0, int(self.settings.snapshot_archive_keep_count))
        archives = [
            item
            for item in self.settings.snapshot_dir.iterdir()
            if item.is_dir() and item.name != "latest"
        ]
        archives.sort(key=lambda item: item.name, reverse=True)
        for stale in archives[keep:]:
            shutil.rmtree(stale, ignore_errors=True)
