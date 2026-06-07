from abc import ABC, abstractmethod

from app.platforms.schemas import CommentRecord, CrawlContext, SearchRequest, VideoRecord


class PlatformAdapter(ABC):
    @abstractmethod
    def search_videos(self, request: SearchRequest) -> tuple[list[VideoRecord], str | None]:
        raise NotImplementedError

    @abstractmethod
    def fetch_comments(
        self,
        platform_video_id: str,
        cursor: str | None = None,
        context: CrawlContext | None = None,
    ) -> tuple[list[CommentRecord], str | None]:
        raise NotImplementedError

    @abstractmethod
    def fetch_replies(
        self,
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None = None,
        context: CrawlContext | None = None,
    ) -> tuple[list[CommentRecord], str | None]:
        raise NotImplementedError
