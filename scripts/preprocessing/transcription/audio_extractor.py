#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


class AudioExtractor:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_audio(self, video_path: str, video_id: str, overwrite: bool = False) -> str:
        output_path = self.output_dir / f"{video_id}.mp3"
        if output_path.exists() and not overwrite:
            return str(output_path)

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "96k",
            str(output_path),
        ]
        subprocess.run(command, check=True)
        return str(output_path)
