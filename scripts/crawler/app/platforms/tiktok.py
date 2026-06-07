from app.core.enums import Platform
from app.platforms.douyin import DouyinAdapter


class TikTokAdapter(DouyinAdapter):
    """TikTok shares the same normalized shape for the MVP skeleton."""

    def _normalize_video(self, item: dict):
        record = super()._normalize_video(item)
        record.platform = Platform.TIKTOK
        return record

    def _normalize_comment(self, item: dict, level: int, root_id: str | None = None):
        record = super()._normalize_comment(item, level=level, root_id=root_id)
        record.platform = Platform.TIKTOK
        return record

