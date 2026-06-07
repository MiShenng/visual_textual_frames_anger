#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import functools
import json
import math
import os
import random
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


DEFAULT_INPUT_CSV = Path("data/raw/videos_source/final_keep_videos_round2_flat.csv")
DEFAULT_VIDEO_DIR = Path("data/raw/videos_source/douyin")
DEFAULT_OUTPUT_ROOT = Path("outputs/frame_extraction")
DEFAULT_RUNS_SUBDIR = "切片结果"
DEFAULT_SAMPLE_SIZE = 20
DEFAULT_FPS = 1.0
DEFAULT_SEED = 20260323
DEFAULT_PHASH_THRESHOLD = 12
DEFAULT_WORKERS = max(1, min(os.cpu_count() or 1, 8))


@dataclass
class VideoRow:
    row_index: int
    selected_from: str
    platform: str
    platform_video_id: str
    author_name: str
    title: str
    description: str
    published_at: str
    matched_queries: str
    video_path: str
    source_row: dict[str, str]


@dataclass
class FrameInfo:
    frame_index: int
    timestamp_seconds: float
    path: str
    relative_path: str
    phash_hex: str
    phash_int: int
    sharpness: float
    width: int
    height: int


@dataclass
class SegmentInfo:
    segment_index: int
    start_second: float
    end_second: float
    duration_seconds: float
    frame_count: int
    representative_frame_index: int
    representative_timestamp_seconds: float
    representative_sharpness: float
    representative_frame_path: str
    representative_frame_relative_path: str
    frame_indices: list[int]
    frame_relative_paths: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按论文方法对短视频执行 1fps 抽帧、相邻帧 pHash 去重和代表帧选择。"
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--phash-threshold", type=int, default=DEFAULT_PHASH_THRESHOLD)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="忽略 sample-size，对所有未 remove=1 且本地视频存在的记录执行处理。",
    )
    return parser.parse_args()


def load_candidate_videos(csv_path: Path, video_dir: Path) -> list[VideoRow]:
    candidates: list[VideoRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            if (row.get("remove") or "").strip() == "1":
                continue
            video_id = (row.get("platform_video_id") or "").strip()
            if not video_id:
                continue
            video_path = video_dir / f"{video_id}.mp4"
            if not video_path.exists():
                continue
            candidates.append(
                VideoRow(
                    row_index=row_index,
                    selected_from=(row.get("selected_from") or "").strip(),
                    platform=(row.get("platform") or "").strip(),
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
    return candidates


def choose_videos(candidates: list[VideoRow], sample_size: int, seed: int, process_all: bool) -> list[VideoRow]:
    if process_all:
        return list(candidates)
    if sample_size >= len(candidates):
        ordered = list(candidates)
        random.Random(seed).shuffle(ordered)
        return ordered
    rng = random.Random(seed)
    ordered = list(candidates)
    rng.shuffle(ordered)
    return ordered


def make_run_dir(output_root: Path, run_name: str, process_all: bool, sample_size: int, seed: int) -> Path:
    runs_root = output_root / DEFAULT_RUNS_SUBDIR
    runs_root.mkdir(parents=True, exist_ok=True)
    if run_name:
        name = run_name
    else:
        prefix = "all" if process_all else f"sample{sample_size}"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{prefix}_{stamp}_seed{seed}"
    run_dir = runs_root / name
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe_duration_seconds(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return float(result.stdout.strip() or 0.0)


def extract_frames(video_path: Path, frames_dir: Path, fps: float) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "frame_%06d.jpg"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "2",
        str(pattern),
    ]
    run_command(command)
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if frames:
        return frames
    fallback = frames_dir / "frame_000001.jpg"
    fallback_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(fallback),
    ]
    run_command(fallback_command)
    return sorted(frames_dir.glob("frame_*.jpg"))


@functools.lru_cache(maxsize=8)
def dct_matrix(size: int) -> np.ndarray:
    matrix = np.zeros((size, size), dtype=np.float32)
    factor = math.pi / (2.0 * size)
    scale0 = math.sqrt(1.0 / size)
    scale = math.sqrt(2.0 / size)
    for k in range(size):
        alpha = scale0 if k == 0 else scale
        for n in range(size):
            matrix[k, n] = alpha * math.cos((2 * n + 1) * k * factor)
    return matrix


def compute_phash(image: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> tuple[int, str]:
    size = hash_size * highfreq_factor
    gray = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float32)
    basis = dct_matrix(size)
    transformed = basis @ pixels @ basis.T
    low_freq = transformed[:hash_size, :hash_size]
    flat = low_freq.flatten()
    median = float(np.median(flat[1:]))
    bits = low_freq > median
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bool(bit))
    width = (hash_size * hash_size) // 4
    return value, f"{value:0{width}x}"


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def variance_of_laplacian(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    padded = np.pad(gray, 1, mode="edge")
    laplacian = (
        padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
        - 4 * padded[1:-1, 1:-1]
    )
    return float(laplacian.var())


def build_frame_infos(frame_paths: Iterable[Path], fps: float, run_dir: Path) -> list[FrameInfo]:
    frame_infos: list[FrameInfo] = []
    for index, frame_path in enumerate(sorted(frame_paths)):
        with Image.open(frame_path) as image:
            phash_int, phash_hex = compute_phash(image)
            sharpness = variance_of_laplacian(image)
            width, height = image.size
        relative_path = frame_path.relative_to(run_dir).as_posix()
        frame_infos.append(
            FrameInfo(
                frame_index=index,
                timestamp_seconds=index / fps,
                path=str(frame_path),
                relative_path=relative_path,
                phash_hex=phash_hex,
                phash_int=phash_int,
                sharpness=sharpness,
                width=width,
                height=height,
            )
        )
    return frame_infos


def segment_adjacent_frames(frame_infos: list[FrameInfo], fps: float, phash_threshold: int) -> list[list[FrameInfo]]:
    if not frame_infos:
        return []
    segments: list[list[FrameInfo]] = [[frame_infos[0]]]
    for previous, current in zip(frame_infos, frame_infos[1:]):
        if hamming_distance(previous.phash_int, current.phash_int) <= phash_threshold:
            segments[-1].append(current)
        else:
            segments.append([current])
    return segments


def to_segment_infos(
    segments: list[list[FrameInfo]],
    representatives_dir: Path,
    run_dir: Path,
    fps: float,
) -> list[SegmentInfo]:
    representatives_dir.mkdir(parents=True, exist_ok=True)
    segment_infos: list[SegmentInfo] = []
    for segment_index, segment_frames in enumerate(segments):
        representative = max(segment_frames, key=lambda item: item.sharpness)
        representative_target = representatives_dir / f"segment_{segment_index:04d}_rep.jpg"
        shutil.copy2(representative.path, representative_target)
        relative_target = representative_target.relative_to(run_dir).as_posix()
        start_second = segment_frames[0].timestamp_seconds
        end_second = segment_frames[-1].timestamp_seconds + (1.0 / fps)
        segment_infos.append(
            SegmentInfo(
                segment_index=segment_index,
                start_second=start_second,
                end_second=end_second,
                duration_seconds=end_second - start_second,
                frame_count=len(segment_frames),
                representative_frame_index=representative.frame_index,
                representative_timestamp_seconds=representative.timestamp_seconds,
                representative_sharpness=representative.sharpness,
                representative_frame_path=str(representative_target),
                representative_frame_relative_path=relative_target,
                frame_indices=[item.frame_index for item in segment_frames],
                frame_relative_paths=[item.relative_path for item in segment_frames],
            )
        )
    return segment_infos


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def process_video(
    video: VideoRow,
    run_dir: Path,
    fps: float,
    phash_threshold: int,
) -> dict[str, object]:
    video_root = run_dir / "videos" / video.platform_video_id
    raw_frames_dir = video_root / "raw_frames"
    representatives_dir = video_root / "representative_frames"
    video_root.mkdir(parents=True, exist_ok=True)

    video_path = Path(video.video_path)
    duration_seconds = probe_duration_seconds(video_path)
    frame_paths = extract_frames(video_path, raw_frames_dir, fps)
    frame_infos = build_frame_infos(frame_paths, fps=fps, run_dir=run_dir)
    segments = segment_adjacent_frames(frame_infos, fps=fps, phash_threshold=phash_threshold)
    segment_infos = to_segment_infos(segments, representatives_dir=representatives_dir, run_dir=run_dir, fps=fps)

    frame_rows = [
        {
            "frame_index": frame.frame_index,
            "timestamp_seconds": round(frame.timestamp_seconds, 3),
            "relative_path": frame.relative_path,
            "phash_hex": frame.phash_hex,
            "sharpness": round(frame.sharpness, 4),
            "width": frame.width,
            "height": frame.height,
        }
        for frame in frame_infos
    ]
    segment_rows = [
        {
            "segment_index": segment.segment_index,
            "start_second": round(segment.start_second, 3),
            "end_second": round(segment.end_second, 3),
            "duration_seconds": round(segment.duration_seconds, 3),
            "frame_count": segment.frame_count,
            "representative_frame_index": segment.representative_frame_index,
            "representative_timestamp_seconds": round(segment.representative_timestamp_seconds, 3),
            "representative_sharpness": round(segment.representative_sharpness, 4),
            "representative_frame_relative_path": segment.representative_frame_relative_path,
            "frame_indices": "|".join(str(value) for value in segment.frame_indices),
            "frame_relative_paths": "|".join(segment.frame_relative_paths),
        }
        for segment in segment_infos
    ]

    write_csv(video_root / "frames.csv", frame_rows)
    write_csv(video_root / "segments.csv", segment_rows)
    write_json(
        video_root / "segments.json",
        {
            "video": {
                "platform_video_id": video.platform_video_id,
                "author_name": video.author_name,
                "title": video.title,
                "description": video.description,
                "published_at": video.published_at,
                "selected_from": video.selected_from,
                "matched_queries": video.matched_queries,
                "video_path": video.video_path,
                "duration_seconds": round(duration_seconds, 3),
                "fps": fps,
                "phash_threshold": phash_threshold,
            },
            "frames": frame_rows,
            "segments": segment_rows,
        },
    )

    raw_frame_count = len(frame_infos)
    segment_count = len(segment_infos)
    compression_ratio = (raw_frame_count / segment_count) if segment_count else 0.0
    return {
        "platform_video_id": video.platform_video_id,
        "author_name": video.author_name,
        "title": video.title,
        "selected_from": video.selected_from,
        "published_at": video.published_at,
        "matched_queries": video.matched_queries,
        "video_path": video.video_path,
        "duration_seconds": round(duration_seconds, 3),
        "raw_frame_count": raw_frame_count,
        "segment_count": segment_count,
        "compression_ratio": round(compression_ratio, 3),
        "representative_frame_dir": representatives_dir.relative_to(run_dir).as_posix(),
        "video_output_dir": video_root.relative_to(run_dir).as_posix(),
    }


def process_video_task(
    video: VideoRow,
    run_dir_str: str,
    fps: float,
    phash_threshold: int,
) -> dict[str, object]:
    return process_video(video, run_dir=Path(run_dir_str), fps=fps, phash_threshold=phash_threshold)


def update_latest_run(output_root: Path, run_dir: Path, summary: dict[str, object]) -> None:
    latest_path = output_root / "latest_run.json"
    write_json(
        latest_path,
        {
            "run_dir": str(run_dir),
            "run_name": run_dir.name,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
        },
    )


def run_serial(
    videos: list[VideoRow],
    run_dir: Path,
    fps: float,
    phash_threshold: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    selected_rows: list[dict[str, object]] = []
    video_summaries: list[dict[str, object]] = []
    failed_rows: list[dict[str, object]] = []

    for index, video in enumerate(videos, start=1):
        print(f"[{index}/{len(videos)}] processing {video.platform_video_id} {video.author_name}")
        try:
            summary_row = process_video(video, run_dir=run_dir, fps=fps, phash_threshold=phash_threshold)
        except Exception as exc:  # noqa: BLE001
            failed_rows.append(
                {
                    "row_index": video.row_index,
                    "platform_video_id": video.platform_video_id,
                    "author_name": video.author_name,
                    "title": video.title,
                    "video_path": video.video_path,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            print(f"  failed: {video.platform_video_id} {type(exc).__name__}: {exc}")
            continue

        selected_rows.append(
            {
                "row_index": video.row_index,
                "selected_from": video.selected_from,
                "platform": video.platform,
                "platform_video_id": video.platform_video_id,
                "author_name": video.author_name,
                "title": video.title,
                "published_at": video.published_at,
                "matched_queries": video.matched_queries,
                "video_path": video.video_path,
            }
        )
        video_summaries.append(summary_row)

    return selected_rows, video_summaries, failed_rows


def run_parallel(
    videos: list[VideoRow],
    run_dir: Path,
    fps: float,
    phash_threshold: int,
    workers: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    selected_rows: list[dict[str, object]] = []
    video_summaries: list[dict[str, object]] = []
    failed_rows: list[dict[str, object]] = []
    order_map = {video.platform_video_id: index for index, video in enumerate(videos)}

    print(f"parallel slicing with workers={workers}, videos={len(videos)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                process_video_task,
                video,
                str(run_dir),
                fps,
                phash_threshold,
            ): video
            for video in videos
        }
        for completed_index, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            video = future_map[future]
            try:
                summary_row = future.result()
            except Exception as exc:  # noqa: BLE001
                failed_rows.append(
                    {
                        "row_index": video.row_index,
                        "platform_video_id": video.platform_video_id,
                        "author_name": video.author_name,
                        "title": video.title,
                        "video_path": video.video_path,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                print(f"[{completed_index}/{len(videos)}] failed {video.platform_video_id} {type(exc).__name__}: {exc}")
                continue

            selected_rows.append(
                {
                    "row_index": video.row_index,
                    "selected_from": video.selected_from,
                    "platform": video.platform,
                    "platform_video_id": video.platform_video_id,
                    "author_name": video.author_name,
                    "title": video.title,
                    "published_at": video.published_at,
                    "matched_queries": video.matched_queries,
                    "video_path": video.video_path,
                }
            )
            video_summaries.append(summary_row)
            print(f"[{completed_index}/{len(videos)}] done {video.platform_video_id}")

    selected_rows.sort(key=lambda row: order_map[row["platform_video_id"]])
    video_summaries.sort(key=lambda row: order_map[row["platform_video_id"]])
    failed_rows.sort(key=lambda row: order_map[row["platform_video_id"]])
    return selected_rows, video_summaries, failed_rows


def main() -> None:
    args = parse_args()
    candidates = load_candidate_videos(args.input_csv, args.video_dir)
    if not candidates:
        raise SystemExit("没有可处理的视频。请先确认输入表和视频目录。")
    ordered_candidates = choose_videos(candidates, args.sample_size, args.seed, args.process_all)
    target_count = len(candidates) if args.process_all else min(args.sample_size, len(candidates))
    run_dir = make_run_dir(args.output_root, args.run_name, args.process_all, target_count, args.seed)
    target_videos = ordered_candidates[:target_count]
    if args.process_all and args.workers > 1:
        selected_rows, video_summaries, failed_rows = run_parallel(
            target_videos,
            run_dir=run_dir,
            fps=args.fps,
            phash_threshold=args.phash_threshold,
            workers=args.workers,
        )
    else:
        selected_rows, video_summaries, failed_rows = run_serial(
            target_videos,
            run_dir=run_dir,
            fps=args.fps,
            phash_threshold=args.phash_threshold,
        )

    write_csv(run_dir / "sample_videos.csv", selected_rows)
    if failed_rows:
        write_csv(run_dir / "failed_videos.csv", failed_rows)
        write_json(run_dir / "failed_videos.json", failed_rows)

    write_csv(run_dir / "video_summary.csv", video_summaries)
    run_summary = {
        "run_name": run_dir.name,
        "input_csv": str(args.input_csv),
        "video_dir": str(args.video_dir),
        "requested_sample_size": target_count,
        "candidate_video_count": len(candidates),
        "process_all": bool(args.process_all),
        "fps": args.fps,
        "phash_threshold": args.phash_threshold,
        "workers": args.workers,
        "seed": args.seed,
        "attempted_video_count": len(video_summaries) + len(failed_rows),
        "video_count_processed": len(video_summaries),
        "failed_video_count": len(failed_rows),
        "total_raw_frames": sum(int(row["raw_frame_count"]) for row in video_summaries),
        "total_segments": sum(int(row["segment_count"]) for row in video_summaries),
    }
    write_json(run_dir / "run_summary.json", run_summary)
    update_latest_run(args.output_root, run_dir, run_summary)
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
