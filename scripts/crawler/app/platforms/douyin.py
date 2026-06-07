from datetime import datetime, timezone

from app.core.enums import Platform
from app.platforms.base import PlatformAdapter
from app.platforms.provider import ProviderClient
from app.platforms.schemas import CommentRecord, SearchRequest, VideoRecord


def _dt_from_timestamp(value: int | float | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


class DouyinAdapter(PlatformAdapter):
    def __init__(self, provider: ProviderClient):
        self.provider = provider

    def search_videos(self, request: SearchRequest) -> tuple[list[VideoRecord], str | None]:
        payloads, cursor = self.provider.search(
            platform=request.platform,
            query_type=request.query_type,
            query=request.query,
            time_range=request.time_range,
            limit=request.limit,
            cursor=request.cursor,
            crawl_context=request.context,
        )
        return [self._normalize_video(item) for item in payloads], cursor

    def fetch_comments(
        self,
        platform_video_id: str,
        cursor: str | None = None,
        context=None,
    ) -> tuple[list[CommentRecord], str | None]:
        payloads, next_cursor = self.provider.comments(
            platform=Platform.DOUYIN,
            platform_video_id=platform_video_id,
            cursor=cursor,
            crawl_context=context,
        )
        return [self._normalize_comment(item, level=1) for item in payloads], next_cursor

    def fetch_replies(
        self,
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None = None,
        context=None,
    ) -> tuple[list[CommentRecord], str | None]:
        payloads, next_cursor = self.provider.replies(
            platform=Platform.DOUYIN,
            platform_video_id=platform_video_id,
            root_comment_platform_id=root_comment_platform_id,
            cursor=cursor,
            crawl_context=context,
        )
        records = [
            self._normalize_comment(item, level=2, root_id=root_comment_platform_id)
            for item in payloads
        ]
        return records, next_cursor

    def _normalize_video(self, item: dict) -> VideoRecord:
        author = item.get("author", {})
        stats = item.get("statistics") or item.get("stats") or {}
        video = item.get("video") or {}
        play_addr = video.get("play_addr") or {}
        tags = item.get("tags")
        if not tags and item.get("text_extra"):
            tags = [
                extra.get("hashtag_name") or extra.get("hashtag_id") or extra.get("name")
                for extra in item.get("text_extra", [])
                if extra.get("hashtag_name") or extra.get("hashtag_id") or extra.get("name")
            ]
        return VideoRecord(
            platform=Platform.DOUYIN,
            platform_video_id=str(item.get("aweme_id") or item.get("video_id")),
            title=item.get("title") or item.get("desc"),
            description=item.get("desc"),
            download_url=item.get("download_url")
            or play_addr.get("uri")
            or next(iter(play_addr.get("url_list", []) or []), None),
            share_url=item.get("share_url"),
            author_platform_id=str(author.get("uid") or author.get("sec_uid") or ""),
            author_name=author.get("nickname"),
            author_profile_url=author.get("profile_url"),
            author_signature=author.get("signature"),
            author_stats=author.get("statistics"),
            tags=tags or [],
            stats=stats,
            published_at=_dt_from_timestamp(item.get("create_time")),
            raw_json=item,
        )

    def _normalize_comment(
        self, item: dict, level: int, root_id: str | None = None
    ) -> CommentRecord:
        user = item.get("user", {})
        return CommentRecord(
            platform=Platform.DOUYIN,
            platform_comment_id=str(item.get("cid") or item.get("comment_id")),
            text=item.get("text") or "",
            level=level,
            root_comment_platform_id=root_id or str(item.get("cid") or item.get("comment_id")),
            author_platform_id=str(user.get("uid") or ""),
            author_name=user.get("nickname"),
            like_count=item.get("digg_count"),
            reply_count=item.get("reply_comment_total"),
            published_at=_dt_from_timestamp(item.get("create_time")),
            raw_json=item,
        )
