from app.core.enums import Platform, QueryType
from app.platforms.douyin import DouyinAdapter
from app.platforms.provider import NullProviderClient
from app.platforms.schemas import SearchRequest


def test_douyin_video_normalization():
    adapter = DouyinAdapter(NullProviderClient())
    record = adapter._normalize_video(
        {
            "aweme_id": "abc123",
            "desc": "hello world",
            "download_url": "https://example.com/video.mp4",
            "author": {"uid": "u1", "nickname": "alice", "signature": "bio"},
            "statistics": {"digg_count": 10},
            "tags": ["tag1", "tag2"],
            "create_time": 1735689600,
        }
    )
    assert record.platform == Platform.DOUYIN
    assert record.platform_video_id == "abc123"
    assert record.author_name == "alice"
    assert record.tags == ["tag1", "tag2"]


def test_search_request_shape():
    request = SearchRequest(
        platform=Platform.DOUYIN,
        query_type=QueryType.KEYWORD,
        query="新能源",
        limit=20,
    )
    assert request.query == "新能源"
    assert request.limit == 20

