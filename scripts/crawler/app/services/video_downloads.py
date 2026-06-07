from pathlib import Path
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Platform, QueryType
from app.platforms.playwright_provider import _load_state_runtime
from app.storage.models import Account, Video, VideoHit


def pick_video_url(video: Video) -> str | None:
    raw_json = video.raw_json or {}
    candidates = [
        ((raw_json.get("video") or {}).get("play_addr") or {}).get("url_list") or [],
        ((raw_json.get("video") or {}).get("download_addr") or {}).get("url_list") or [],
    ]
    bit_rates = (raw_json.get("video") or {}).get("bit_rate") or []
    for item in bit_rates:
        candidates.append(((item.get("play_addr") or {}).get("url_list")) or [])

    for group in candidates:
        for url in group:
            if isinstance(url, str) and url.startswith("http"):
                return url

    if video.download_url and video.download_url.startswith("http"):
        return video.download_url
    return None


def target_video_path(base_dir: Path, platform: Platform, platform_video_id: str) -> Path:
    safe_video_id = re.sub(r"[^A-Za-z0-9_-]", "_", platform_video_id)
    return base_dir / platform.value / f"{safe_video_id}.mp4"


class VideoDownloadService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def list_videos(
        self,
        platform: Platform | None = None,
        query: str | None = None,
        query_type: QueryType | None = None,
        limit: int | None = None,
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
        stmt = stmt.order_by(Video.created_at.asc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def download_videos(
        self,
        platform: Platform | None = None,
        query: str | None = None,
        query_type: QueryType | None = None,
        limit: int | None = None,
        overwrite: bool = False,
    ) -> dict[str, int]:
        videos = self.list_videos(platform=platform, query=query, query_type=query_type, limit=limit)
        downloaded = 0
        skipped = 0
        failed = 0
        for video in videos:
            url = pick_video_url(video)
            if not url:
                failed += 1
                continue
            target = target_video_path(
                self.settings.video_store_dir,
                video.platform,
                video.platform_video_id,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not overwrite:
                skipped += 1
                continue
            try:
                self._download_file(url, target)
                downloaded += 1
            except Exception:
                failed += 1
        return {
            "selected": len(videos),
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
        }

    def _download_file(self, url: str, target: Path) -> None:
        headers = self._download_headers()
        temp_path = target.with_suffix(target.suffix + ".part")
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            timeout=120,
            follow_redirects=True,
            trust_env=False,
        ) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        handle.write(chunk)
        temp_path.replace(target)

    def _download_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.settings.playwright_user_agent
            or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
        }
        state_path = self.db.scalar(
            select(Account.login_state_path).where(Account.platform == Platform.DOUYIN).order_by(Account.id.asc())
        )
        if state_path:
            runtime = _load_state_runtime(state_path, headers["User-Agent"])
            headers["Cookie"] = runtime.cookie_header
        return headers
