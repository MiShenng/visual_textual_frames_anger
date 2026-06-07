from __future__ import annotations

import concurrent.futures
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .discovery import TextRecord, discover_text_records
from .io_utils import dump_json, load_json, setup_logger, write_df
from .qwen_client import QwenClient


class TextCodingPipeline:
    def __init__(self, config) -> None:
        self.config = config
        self.logger = setup_logger(config.output.log_dir)
        self.client = QwenClient(config, self.logger)

    def run(self, stage: str = "all") -> None:
        if stage == "all":
            records = self.build_packages()
            self.run_code(records=records)
            self.export_codes(records=records)
            return
        if stage == "package":
            self.build_packages()
            return
        if stage == "code":
            self.run_code()
            return
        if stage == "export":
            self.export_codes()
            return
        raise ValueError(f"未知 stage: {stage}")

    def build_packages(self) -> list[TextRecord]:
        records = discover_text_records(
            reference_path=self.config.input.reference_csv_path,
            transcript_path=self.config.input.transcript_summary_path,
            ocr_path=self.config.input.ocr_text_table_path,
            logger=self.logger,
        )
        rows: list[dict[str, Any]] = []
        for record in records:
            package_json_path = self.config.package_json_dir / f"{record.video_id}.json"
            package_txt_path = self.config.package_txt_dir / f"{record.video_id}.txt"
            payload = {
                **record.to_dict(),
                "text_length_chars": len(record.text_material),
                "created_at": self._created_at(),
                "package_json_path": str(package_json_path),
                "package_txt_path": str(package_txt_path),
            }
            dump_json(payload, package_json_path)
            package_txt_path.write_text(record.text_material, encoding="utf-8")
            rows.append(
                {
                    "video_id": record.video_id,
                    "title": record.title,
                    "author_name": record.author_name,
                    "publish_time": record.publish_time,
                    "title_text": record.title_text,
                    "transcript_text": record.transcript_text,
                    "subtitle_text": record.subtitle_text,
                    "ocr_text": record.ocr_text,
                    "text_material": record.text_material,
                    "text_length_chars": len(record.text_material),
                    "source_reference_path": record.source_reference_path,
                    "source_transcript_path": record.source_transcript_path,
                    "source_ocr_path": record.source_ocr_path,
                    "package_json_path": str(package_json_path),
                    "package_txt_path": str(package_txt_path),
                    "created_at": payload["created_at"],
                }
            )
        package_df = pd.DataFrame(rows)
        if not package_df.empty:
            package_df = package_df.sort_values("video_id").reset_index(drop=True)
        write_df(package_df, self.config.package_table_csv, self.config.package_table_parquet)
        self.logger.info("文本材料包表已写出: %s", self.config.package_table_csv)
        return records

    def run_code(self, records: list[TextRecord] | None = None) -> None:
        if records is None:
            records = discover_text_records(
                reference_path=self.config.input.reference_csv_path,
                transcript_path=self.config.input.transcript_summary_path,
                ocr_path=self.config.input.ocr_text_table_path,
                logger=self.logger,
            )

        pending: list[TextRecord] = []
        for record in records:
            norm_path = self.config.text_normalized_dir / f"{record.video_id}.json"
            if norm_path.exists() and not self.config.pipeline.overwrite_existing:
                normalized = load_json(norm_path)
                if normalized.get("status") in {"success", "skipped"}:
                    continue
            pending.append(record)

        self.logger.info(
            "待处理文本 %s 条（concurrency=%s）",
            len(pending),
            self.config.api.text_concurrency,
        )
        self._run_parallel(
            records=pending,
            worker=self._code_text_record,
            max_workers=self.config.api.text_concurrency,
            total_items=len(pending),
            unit_of_record=lambda _: 1,
        )

    def export_codes(self, records: list[TextRecord] | None = None) -> None:
        if records is None:
            records = discover_text_records(
                reference_path=self.config.input.reference_csv_path,
                transcript_path=self.config.input.transcript_summary_path,
                ocr_path=self.config.input.ocr_text_table_path,
                logger=self.logger,
            )

        rows = []
        for record in records:
            norm_path = self.config.text_normalized_dir / f"{record.video_id}.json"
            normalized = load_json(norm_path) if norm_path.exists() else {}
            rows.append(
                {
                    "video_id": record.video_id,
                    "title": record.title,
                    "author_name": record.author_name,
                    "publish_time": record.publish_time,
                    "title_text": record.title_text,
                    "transcript_text": record.transcript_text,
                    "subtitle_text": record.subtitle_text,
                    "ocr_text": record.ocr_text,
                    "text_material": record.text_material,
                    "text_length_chars": normalized.get("text_length_chars", len(record.text_material)),
                    "narrative_label": normalized.get("narrative_label", ""),
                    "narrative_confidence": normalized.get("narrative_confidence", ""),
                    "narrative_reason": normalized.get("narrative_reason", ""),
                    "arousal_label": normalized.get("arousal_label", ""),
                    "arousal_confidence": normalized.get("arousal_confidence", ""),
                    "arousal_reason": normalized.get("arousal_reason", ""),
                    "narrative_cues": json.dumps(
                        normalized.get("narrative_cues", [])
                        if isinstance(normalized.get("narrative_cues"), list)
                        else [],
                        ensure_ascii=False,
                    ),
                    "api_model": normalized.get("api_model", ""),
                    "api_raw_json_path": normalized.get("api_raw_json_path")
                    or self._latest_raw_json_path(self.config.text_raw_dir, record.video_id),
                    "request_id": normalized.get("request_id", ""),
                    "status": normalized.get("status", self._infer_status(self.config.text_raw_dir, record.video_id)),
                    "skip_reason": normalized.get("skip_reason", ""),
                    "error": normalized.get("error", ""),
                    "package_json_path": str(self.config.package_json_dir / f"{record.video_id}.json"),
                    "package_txt_path": str(self.config.package_txt_dir / f"{record.video_id}.txt"),
                    "source_reference_path": record.source_reference_path,
                    "source_transcript_path": record.source_transcript_path,
                    "source_ocr_path": record.source_ocr_path,
                    "created_at": normalized.get("created_at", ""),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("video_id").reset_index(drop=True)
        write_df(df, self.config.text_codes_csv, self.config.text_codes_parquet)
        self.logger.info("文本编码结果表已写出: %s", self.config.text_codes_csv)

    def _code_text_record(self, record: TextRecord) -> None:
        out_path = self.config.text_normalized_dir / f"{record.video_id}.json"
        package_json_path = self.config.package_json_dir / f"{record.video_id}.json"
        package_txt_path = self.config.package_txt_dir / f"{record.video_id}.txt"
        payload = {
            **record.to_dict(),
            "text_length_chars": len(record.text_material),
            "text_material_package_path": str(package_json_path),
            "text_material_txt_path": str(package_txt_path),
            "created_at": self._created_at(),
        }
        if not record.text_material.strip():
            payload.update(
                {
                    "status": "skipped",
                    "skip_reason": "empty_text_material",
                    "error": "",
                    "api_raw_json_path": "",
                }
            )
            dump_json(payload, out_path)
            self.logger.warning("文本材料为空，跳过: %s", record.video_id)
            return

        try:
            result = self.client.code_text(payload, self.config.text_raw_dir)
            payload.update(
                {
                    "status": "success",
                    "skip_reason": "",
                    "error": "",
                    "narrative_label": result["narrative_label"],
                    "narrative_confidence": result["narrative_confidence"],
                    "narrative_reason": result["narrative_reason"],
                    "arousal_label": result["arousal_label"],
                    "arousal_confidence": result["arousal_confidence"],
                    "arousal_reason": result["arousal_reason"],
                    "narrative_cues": result["narrative_cues"],
                    "api_model": result["model"],
                    "api_raw_json_path": result["raw_json_path"],
                    "request_id": result["request_id"],
                    "response_content": result["response_content"],
                }
            )
            dump_json(payload, out_path)
            self.logger.info("文本编码成功: %s", record.video_id)
        except Exception as exc:
            payload.update(
                {
                    "status": "failed",
                    "skip_reason": "",
                    "error": str(exc),
                    "api_raw_json_path": self._latest_raw_json_path(self.config.text_raw_dir, record.video_id),
                }
            )
            dump_json(payload, out_path)
            self.logger.error("文本编码失败: %s | %s", record.video_id, exc)

    def _run_parallel(
        self,
        records,
        worker,
        max_workers: int,
        total_items: int | None = None,
        unit_of_record: Callable[[Any], int] | None = None,
    ) -> None:
        if not records:
            return
        total = total_items if total_items is not None else len(records)
        done = 0
        started_at = time.monotonic()
        self._render_progress(done=done, total=total, started_at=started_at)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(worker, record): record for record in records}
            for future in concurrent.futures.as_completed(future_map):
                record = future_map[future]
                try:
                    future.result()
                except Exception as exc:
                    self.logger.error("处理失败 | item=%s | %s", getattr(record, "video_id", "UNKNOWN"), exc)
                step = unit_of_record(record) if unit_of_record else 1
                done = min(total, done + max(step, 0))
                self._render_progress(done=done, total=total, started_at=started_at)
        if total > 0:
            sys.stdout.write("\n")
            sys.stdout.flush()

    @staticmethod
    def _created_at() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _latest_raw_json_path(raw_dir: Path, item_id: str) -> str:
        matches = sorted(raw_dir.glob(f"{item_id}__attempt_*.json"))
        return str(matches[-1]) if matches else ""

    @staticmethod
    def _infer_status(raw_dir: Path, item_id: str) -> str:
        if list(raw_dir.glob(f"{item_id}__attempt_*.json")):
            return "failed"
        return "pending"

    @staticmethod
    def _render_progress(done: int, total: int, started_at: float) -> None:
        if total <= 0:
            return
        elapsed = max(time.monotonic() - started_at, 0.001)
        percent = min(max(done / total, 0.0), 1.0)
        remaining = max(total - done, 0)
        bar_width = 24
        filled = int(bar_width * percent)
        bar = "█" * filled + "░" * (bar_width - filled)

        if done <= 0:
            eta_text = "--:--:--"
            finish_text = "--:--:--"
        else:
            eta_seconds = int((elapsed / done) * remaining)
            eta_text = TextCodingPipeline._format_seconds(eta_seconds)
            finish_time = datetime.now().astimezone().timestamp() + eta_seconds
            finish_text = datetime.fromtimestamp(finish_time).astimezone().strftime("%H:%M:%S")

        line = (
            f"\r进度 [{bar}] {percent * 100:6.2f}% | "
            f"已完成 {done}/{total} | 剩余 {remaining} | "
            f"ETA {eta_text} | 预计完成 {finish_text}"
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    @staticmethod
    def _format_seconds(seconds: int) -> str:
        seconds = max(int(seconds), 0)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

