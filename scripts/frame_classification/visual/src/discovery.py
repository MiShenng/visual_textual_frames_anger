from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SliceRecord:
    slice_id: str
    video_id: str
    run_name: str
    segment_index: int
    start_second: float
    end_second: float
    duration_seconds: float
    image_path: str
    segments_source_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def discover_slice_records(slice_results_dir: Path, logger) -> list[SliceRecord]:
    segment_jsons = _latest_by_video(
        p for p in slice_results_dir.rglob("segments.json") if not p.name.startswith("._")
    )
    records: list[SliceRecord] = []
    for path in segment_jsons:
        records.extend(_load_from_json(path, logger))
    logger.info("发现视频 %s 个，切片 %s 条。", len(segment_jsons), len(records))
    return records


def _latest_by_video(paths: Iterable[Path]) -> list[Path]:
    latest: dict[str, Path] = {}
    for path in paths:
        video_id = path.parent.name
        current = latest.get(video_id)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            latest[video_id] = path
    return sorted(latest.values(), key=lambda p: p.parent.name)


def _load_from_json(path: Path, logger) -> list[SliceRecord]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            logger.warning("segments.json 读取失败，回退 CSV: %s", csv_path)
            return _load_from_csv(csv_path)
        raise

    video = data.get("video") or {}
    segments = data.get("segments") or []
    video_id = str(video.get("platform_video_id") or path.parent.name)
    run_name = path.parents[1].name if len(path.parents) > 1 else ""
    records: list[SliceRecord] = []
    for seg in segments:
        segment_index = int(seg.get("segment_index", 0))
        image_path = _resolve_image_path(path, str(seg.get("representative_frame_relative_path", "")))
        records.append(
            SliceRecord(
                slice_id=f"{video_id}__segment_{segment_index:04d}",
                video_id=video_id,
                run_name=run_name,
                segment_index=segment_index,
                start_second=float(seg.get("start_second", 0.0)),
                end_second=float(seg.get("end_second", 0.0)),
                duration_seconds=float(seg.get("duration_seconds", 0.0)),
                image_path=str(image_path) if image_path else "",
                segments_source_path=str(path),
            )
        )
    return records


def _load_from_csv(path: Path) -> list[SliceRecord]:
    video_id = path.parent.name
    run_name = path.parents[1].name if len(path.parents) > 1 else ""
    records: list[SliceRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            segment_index = int(float(row.get("segment_index", 0) or 0))
            image_path = _resolve_image_path(path, str(row.get("representative_frame_relative_path", "")))
            records.append(
                SliceRecord(
                    slice_id=f"{video_id}__segment_{segment_index:04d}",
                    video_id=video_id,
                    run_name=run_name,
                    segment_index=segment_index,
                    start_second=float(row.get("start_second", 0.0) or 0.0),
                    end_second=float(row.get("end_second", 0.0) or 0.0),
                    duration_seconds=float(row.get("duration_seconds", 0.0) or 0.0),
                    image_path=str(image_path) if image_path else "",
                    segments_source_path=str(path),
                )
            )
    return records


def _resolve_image_path(segments_file: Path, image_rel: str) -> Path | None:
    text = image_rel.strip()
    if not text:
        return None

    candidate = Path(text)
    if candidate.is_absolute():
        return candidate

    probe_roots = [
        segments_file.parents[2] if len(segments_file.parents) > 2 else segments_file.parent,
        segments_file.parents[1] if len(segments_file.parents) > 1 else segments_file.parent,
        segments_file.parent,
    ]
    for root in probe_roots:
        path = (root / text).resolve()
        if path.exists():
            return path
    return (probe_roots[0] / text).resolve()

