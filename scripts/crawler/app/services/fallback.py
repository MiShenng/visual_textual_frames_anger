import httpx

from app.core.config import get_settings
from app.core.enums import Platform, QueryType
from app.platforms.schemas import CommentRecord, SearchRequest, VideoRecord


class FallbackProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def enabled(self) -> bool:
        return bool(
            self.settings.fallback_enabled
            and self.settings.fallback_base_url
            and self.settings.fallback_api_key
        )

    def search(self, request: SearchRequest) -> list[VideoRecord]:
        if not self.enabled():
            return []
        response = httpx.get(
            f"{self.settings.fallback_base_url}/search",
            params={
                "platform": request.platform.value,
                "query_type": request.query_type.value,
                "query": request.query,
                "time_range": request.time_range,
                "limit": request.limit,
                "cursor": request.cursor,
            },
            headers={"Authorization": f"Bearer {self.settings.fallback_api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            VideoRecord(
                platform=Platform(item["platform"]),
                platform_video_id=item["platform_video_id"],
                title=item.get("title"),
                description=item.get("description"),
                download_url=item.get("download_url"),
                share_url=item.get("share_url"),
                author_platform_id=item.get("author_platform_id"),
                author_name=item.get("author_name"),
                author_profile_url=item.get("author_profile_url"),
                author_signature=item.get("author_signature"),
                author_stats=item.get("author_stats"),
                tags=item.get("tags") or [],
                stats=item.get("stats"),
                raw_json=item,
            )
            for item in payload.get("items", [])
        ]

    def comments(
        self,
        platform: Platform,
        platform_video_id: str,
        root_comment_platform_id: str | None = None,
    ) -> list[CommentRecord]:
        if not self.enabled():
            return []
        response = httpx.get(
            f"{self.settings.fallback_base_url}/comments",
            params={
                "platform": platform.value,
                "platform_video_id": platform_video_id,
                "root_comment_platform_id": root_comment_platform_id,
            },
            headers={"Authorization": f"Bearer {self.settings.fallback_api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            CommentRecord(
                platform=platform,
                platform_comment_id=item["platform_comment_id"],
                text=item["text"],
                level=item["level"],
                root_comment_platform_id=item.get("root_comment_platform_id"),
                author_platform_id=item.get("author_platform_id"),
                author_name=item.get("author_name"),
                like_count=item.get("like_count"),
                reply_count=item.get("reply_count"),
                raw_json=item,
            )
            for item in payload.get("items", [])
        ]
