#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tqdm import tqdm

from api_transcriber import APITranscriber
from audio_extractor import AudioExtractor
from video_reader import VideoCSVReader


DEFAULT_CSV = "/Volumes/黎鑿/4.1 AEJMC/数据- 视频原材料/final_keep_videos_round2_flat.csv"
DEFAULT_VIDEO_DIR = "/Volumes/黎鑿/4.1 AEJMC/数据- 视频原材料/douyin"
DEFAULT_OUTPUT_DIR = "/Volumes/黎鑿/4.1 AEJMC/程序- 转录视频文本/output"
DEFAULT_LOG_PATH = "/Volumes/黎鑿/4.1 AEJMC/程序- 转录视频文本/video_text_extractor.log"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(DEFAULT_LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("video_text_main")


def create_directory_structure(base_dir: str) -> Dict[str, str]:
    dirs = {
        "audio": os.path.join(base_dir, "audio_files"),
        "transcripts": os.path.join(base_dir, "transcripts"),
        "temp": os.path.join(base_dir, "temp"),
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs


def merge_all_transcripts(transcripts_dir: str, output_base_dir: str) -> None:
    transcript_root = Path(transcripts_dir)
    if not transcript_root.exists():
        logger.warning("转录目录不存在，跳过合并。")
        return

    dirs = sorted([p for p in transcript_root.iterdir() if p.is_dir()])
    if not dirs:
        logger.warning("没有可合并的转录结果。")
        return

    lines: list[str] = [
        "# 所有视频文本提取结果汇总",
        "",
        f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"共包含 {len(dirs)} 条视频",
        "",
        "---",
        "",
    ]
    for index, directory in enumerate(dirs, start=1):
        md_path = directory / f"{directory.name}.md"
        if not md_path.exists():
            continue
        lines.append(f"## 视频 {index}: {directory.name}")
        lines.append("")
        lines.append(md_path.read_text(encoding="utf-8"))
        lines.append("")
        lines.append("---")
        lines.append("")

    merged_path = Path(output_base_dir) / "merged_transcripts.md"
    merged_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("已生成合并转录文件: %s", merged_path)


def process_videos(
    csv_file: str,
    video_dir: str,
    output_base_dir: str,
    language: str = "zh",
    limit: Optional[int] = None,
    sample_size: Optional[int] = None,
    seed: int = 20260323,
    overwrite_audio: bool = False,
    overwrite_transcript: bool = False,
) -> None:
    dirs = create_directory_structure(output_base_dir)
    reader = VideoCSVReader(csv_file, video_dir)
    videos = reader.read_videos(limit=limit, sample_size=sample_size, seed=seed)
    logger.info("读取到 %s 条本地视频记录。", len(videos))

    extractor = AudioExtractor(dirs["audio"])
    transcriber = APITranscriber(language=language)

    failures: list[dict[str, Any]] = []
    start_time = time.time()
    pbar = tqdm(
        total=len(videos),
        desc="🎬 视频文本提取",
        unit="视频",
        ncols=140,
        dynamic_ncols=True,
        colour="cyan",
    )

    for index, video in enumerate(videos, start=1):
        video_transcript_dir = Path(dirs["transcripts"]) / video.platform_video_id
        target_json = video_transcript_dir / f"{video.platform_video_id}.json"
        if target_json.exists() and not overwrite_transcript:
            logger.info("跳过已存在转录: %s", video.platform_video_id)
            pbar.update(1)
            continue

        try:
            logger.info("[%s/%s] 处理视频 %s %s", index, len(videos), video.platform_video_id, video.author_name)
            audio_path = extractor.extract_audio(video.video_path, video.platform_video_id, overwrite=overwrite_audio)
            transcript = transcriber.transcribe_audio(audio_path)
            transcriber.save_transcript_bundle(
                transcript=transcript,
                output_dir=dirs["transcripts"],
                video_id=video.platform_video_id,
                metadata={
                    "platform_video_id": video.platform_video_id,
                    "author_name": video.author_name,
                    "title": video.title,
                    "published_at": video.published_at,
                    "matched_queries": video.matched_queries,
                    "video_path": video.video_path,
                    "audio_path": audio_path,
                },
            )
            time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            logger.error("处理视频失败 %s: %s", video.platform_video_id, exc)
            failures.append(
                {
                    "platform_video_id": video.platform_video_id,
                    "author_name": video.author_name,
                    "title": video.title,
                    "video_path": video.video_path,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        finally:
            pbar.update(1)

    pbar.close()

    if failures:
        import csv

        failed_path = Path(output_base_dir) / "failed_videos.csv"
        with failed_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(failures[0].keys()))
            writer.writeheader()
            writer.writerows(failures)
        logger.warning("共有 %s 条失败记录，已写入 %s", len(failures), failed_path)

    merge_all_transcripts(dirs["transcripts"], output_base_dir)

    elapsed = time.time() - start_time
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    logger.info("工作流程完成，总耗时: %s小时 %s分钟 %.2f秒", int(hours), int(minutes), seconds)
def main() -> None:
    parser = argparse.ArgumentParser(description="本地短视频转文本自动化流程（API版）")
    parser.add_argument("--csv-file", default=DEFAULT_CSV, help="视频参考表路径")
    parser.add_argument("--video-dir", default=DEFAULT_VIDEO_DIR, help="本地 mp4 目录")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--language", "-l", default="zh", help="转写语言，默认 zh")
    parser.add_argument("--limit", type=int, help="最多处理多少条视频")
    parser.add_argument("--sample-size", type=int, help="随机抽取多少条做测试")
    parser.add_argument("--seed", type=int, default=20260323, help="随机种子")
    parser.add_argument("--overwrite-audio", action="store_true", help="覆盖已抽出的音频")
    parser.add_argument("--overwrite-transcript", action="store_true", help="覆盖已存在的转写结果")
    args = parser.parse_args()

    process_videos(
        csv_file=args.csv_file,
        video_dir=args.video_dir,
        output_base_dir=args.output_dir,
        language=args.language,
        limit=args.limit,
        sample_size=args.sample_size,
        seed=args.seed,
        overwrite_audio=args.overwrite_audio,
        overwrite_transcript=args.overwrite_transcript,
    )


if __name__ == "__main__":
    main()
