from abc import ABC, abstractmethod

from app.core.enums import Platform, QueryType
from app.platforms.schemas import CrawlContext


class ProviderClient(ABC):
    @abstractmethod
    def search(
        self,
        platform: Platform,
        query_type: QueryType,
        query: str,
        time_range: str | None,
        limit: int | None,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        raise NotImplementedError

    @abstractmethod
    def comments(
        self,
        platform: Platform,
        platform_video_id: str,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        raise NotImplementedError

    @abstractmethod
    def replies(
        self,
        platform: Platform,
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        raise NotImplementedError


class NullProviderClient(ProviderClient):
    def search(self, platform, query_type, query, time_range, limit, cursor=None, crawl_context=None):
        return [], None

    def comments(self, platform, platform_video_id, cursor=None, crawl_context=None):
        return [], None

    def replies(
        self,
        platform,
        platform_video_id,
        root_comment_platform_id,
        cursor=None,
        crawl_context=None,
    ):
        return [], None
