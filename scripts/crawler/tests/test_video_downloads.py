from pathlib import Path

from app.core.enums import Platform
from app.services.video_downloads import pick_video_url, target_video_path
from app.storage.models import Video


def test_pick_video_url_prefers_http_url_from_raw_json():
    video = Video(
        platform=Platform.DOUYIN,
        platform_video_id="123",
        raw_json={
            "video": {
                "play_addr": {"url_list": ["https://example.com/v1.mp4"]},
                "download_addr": {"url_list": ["https://example.com/v2.mp4"]},
            }
        },
    )

    assert pick_video_url(video) == "https://example.com/v1.mp4"


def test_target_video_path_uses_platform_subdir_and_stable_name():
    path = target_video_path(Path("/tmp/videos"), Platform.DOUYIN, "7579500380678065458")

    assert path == Path("/tmp/videos/douyin/7579500380678065458.mp4")
