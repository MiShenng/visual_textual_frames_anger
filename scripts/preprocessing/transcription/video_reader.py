#!/usr/bin/env python3
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class VideoItem:
    platform_video_id: str
    author_name: str
    title: str
    description: str
    published_at: str
    matched_queries: str
    video_path: str
    source_row: dict[str, str]


class VideoCSVReader:
    def __init__(self, csv_path: str, video_dir: str):
        self.csv_path = Path(csv_path)
        self.video_dir = Path(video_dir)

    def read_videos(self, limit: Optional[int] = None, sample_size: Optional[int] = None, seed: int = 20260323) -> list[VideoItem]:
        rows: list[VideoItem] = []
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if (row.get("remove") or "").strip() == "1":
                    continue
                video_id = (row.get("platform_video_id") or "").strip()
                if not video_id:
                    continue
                video_path = self.video_dir / f"{video_id}.mp4"
                if not video_path.exists():
                    continue
                rows.append(
                    VideoItem(
                        platform_video_id=video_id,
                        author_name=(row.get("author_name") or "").strip(),
                        title=(row.get("title") or "").strip(),
                        description=(row.get("description") or "").strip(),
                        published_at=(row.get("published_at") or "").strip(),
                        matched_queries=(row.get("matched_queries") or "").strip(),
                        video_path=str(video_path),
                        source_row=row,
                    )
                )

        if sample_size is not None and sample_size < len(rows):
            rng = random.Random(seed)
            rows = rng.sample(rows, sample_size)

        if limit is not None:
            rows = rows[:limit]
        return rows
