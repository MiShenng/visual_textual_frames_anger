from app.core.enums import Platform
from app.platforms.base import PlatformAdapter
from app.platforms.douyin import DouyinAdapter
from app.platforms.playwright_provider import PlaywrightProviderClient
from app.platforms.provider import ProviderClient
from app.platforms.tiktok import TikTokAdapter


class AdapterRegistry:
    def __init__(self, provider: ProviderClient | None = None):
        actual_provider = provider or PlaywrightProviderClient()
        self.adapters: dict[Platform, PlatformAdapter] = {
            Platform.DOUYIN: DouyinAdapter(actual_provider),
            Platform.TIKTOK: TikTokAdapter(actual_provider),
        }

    def get(self, platform: Platform) -> PlatformAdapter:
        return self.adapters[platform]
