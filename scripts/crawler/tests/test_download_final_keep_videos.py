import csv
from pathlib import Path

from scripts import download_final_keep_videos as downloader


def test_load_selected_video_ids_dedupes_and_preserves_order(tmp_path: Path):
    source = tmp_path / "videos.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["platform_video_id"])
        writer.writeheader()
        writer.writerow({"platform_video_id": "v1"})
        writer.writerow({"platform_video_id": "v2"})
        writer.writerow({"platform_video_id": "v1"})
        writer.writerow({"platform_video_id": "v3"})

    assert downloader.load_selected_video_ids(source) == ["v1", "v2", "v3"]
    assert downloader.load_selected_video_ids(source, limit=2) == ["v1", "v2"]


def test_unresolved_failed_ids_skips_downloaded_targets(tmp_path: Path):
    target_dir = tmp_path / "videos"
    target_dir.mkdir()
    (target_dir / "v2.mp4").write_bytes(b"ok")
    failed = {"v1": "goto timeout", "v2": "hidden video", "v3": "meta failed"}
    attempts = {"v1": 1, "v2": 1, "v3": 0}

    assert downloader.unresolved_failed_ids(failed, target_dir, attempts) == ["v1"]


def test_write_failed_csv_only_keeps_unresolved_rows(tmp_path: Path):
    failed_csv = tmp_path / "failed.csv"
    target_dir = tmp_path / "videos"
    target_dir.mkdir()
    (target_dir / "done.mp4").write_bytes(b"x")

    downloader.write_failed_csv(
        failed_csv=failed_csv,
        failed_reasons={"pending": "goto timeout", "done": "hidden video"},
        attempts={"pending": 2, "done": 1},
        target_dir=target_dir,
    )

    with failed_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [{"platform_video_id": "pending", "attempts": "2", "reason": "goto timeout"}]


def test_existing_file_count_ignores_macos_sidecars(tmp_path: Path):
    target_dir = tmp_path / "videos"
    target_dir.mkdir()
    (target_dir / "a.mp4").write_bytes(b"x")
    (target_dir / "._a.mp4").write_bytes(b"y")
    (target_dir / "b.mp4").write_bytes(b"z")

    assert downloader.existing_file_count(target_dir) == 2


def test_is_http_src_only_accepts_http_strings():
    assert downloader.is_http_src("https://example.com/video.mp4") is True
    assert downloader.is_http_src("blob:abc") is False
    assert downloader.is_http_src(None) is False
