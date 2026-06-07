from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from video_reader import VideoCSVReader


class VideoCSVReaderTests(unittest.TestCase):
    def test_read_videos_filters_missing_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            csv_path = root / "videos.csv"
            video_dir = root / "videos"
            video_dir.mkdir()
            (video_dir / "100.mp4").write_bytes(b"fake")
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["platform_video_id", "author_name", "title", "description", "published_at", "matched_queries"],
                )
                writer.writeheader()
                writer.writerow({"platform_video_id": "100", "author_name": "A", "title": "T1", "description": "", "published_at": "", "matched_queries": ""})
                writer.writerow({"platform_video_id": "200", "author_name": "B", "title": "T2", "description": "", "published_at": "", "matched_queries": ""})

            rows = VideoCSVReader(str(csv_path), str(video_dir)).read_videos()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].platform_video_id, "100")


if __name__ == "__main__":
    unittest.main()
