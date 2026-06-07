from __future__ import annotations

import concurrent.futures
import difflib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .discovery import discover_slice_records
from .io_utils import dump_json, load_json, setup_logger, write_df
from .qwen_client import QwenClient


class VisualCodingPipeline:
    def __init__(self, config) -> None:
        self.config = config
        self.logger = setup_logger(config.output.log_dir)
        self.client = QwenClient(config, self.logger)

    def run(self, stage: str = "all") -> None:
        if stage in {"all", "visual"}:
            self.run_visual()
            return
        if stage == "export":
            self.export_only()
            return
        raise ValueError(f"未知 stage: {stage}")

    def run_visual(self) -> None:
        records = discover_slice_records(self.config.input.slice_results_dir, self.logger)
        pending: list[Any] = []
        for record in records:
            norm_path = self.config.visual_normalized_dir / f"{record.slice_id}.json"
            if norm_path.exists() and not self.config.pipeline.overwrite_existing:
                normalized = load_json(norm_path)
                if normalized.get("status") in {"success", "skipped"}:
                    continue
            pending.append(record)

        batches = self._chunked(pending, self.config.api.visual_batch_size)
        self.logger.info(
            "待处理切片 %s 条，分 %s 批（batch_size=%s, concurrency=%s）",
            len(pending),
            len(batches),
            self.config.api.visual_batch_size,
            self.config.api.visual_concurrency,
        )
        self._run_parallel(
            records=batches,
            worker=self._code_visual_batch,
            max_workers=self.config.api.visual_concurrency,
            total_items=len(pending),
            unit_of_record=lambda batch: len(batch),
        )
        self.build_slice_output(records)

    def export_only(self) -> None:
        records = discover_slice_records(self.config.input.slice_results_dir, self.logger)
        self.build_slice_output(records)

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
                    batch_desc = self._batch_desc(record)
                    self.logger.error("处理失败 | batch=%s | %s", batch_desc, exc)
                step = unit_of_record(record) if unit_of_record else 1
                done = min(total, done + max(step, 0))
                self._render_progress(done=done, total=total, started_at=started_at)
        if total > 0:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _code_visual_batch(self, records) -> None:
        prepared: list[tuple[Any, dict[str, Any], Path]] = []
        valid_items: list[dict[str, Any]] = []
        for record in records:
            out_path = self.config.visual_normalized_dir / f"{record.slice_id}.json"
            image_path = Path(record.image_path)
            payload = {
                **record.to_dict(),
                "segment_id": self._segment_id(record.segment_index),
                "file_name": image_path.name if record.image_path else "",
                "start_time": record.start_second,
                "end_time": record.end_second,
                "created_at": self._created_at(),
            }
            if not image_path.exists():
                payload.update(
                    {
                        "status": "skipped",
                        "skip_reason": "missing_image",
                        "error": "",
                        "api_raw_json_path": "",
                    }
                )
                dump_json(payload, out_path)
                self.logger.warning("图片不存在，跳过: %s", image_path)
                continue

            prepared.append((record, payload, out_path))
            valid_items.append(record.to_dict() | payload)

        if not valid_items:
            return

        try:
            results = self.client.code_visual_batch(valid_items, self.config.visual_raw_dir)
            result_map = {item["slice_id"]: item for item in results}
            for record, payload, out_path in prepared:
                result = result_map.get(record.slice_id)
                if not result:
                    raise ValueError(f"批量结果缺少切片: {record.slice_id}")
                payload.update(
                    {
                        "status": "success",
                        "skip_reason": "",
                        "error": "",
                        "visual_label": result["visual_label"],
                        "visual_confidence": result["visual_confidence"],
                        "visual_reason": result["visual_reason"],
                        "arousal_label": result["arousal_label"],
                        "arousal_confidence": result["arousal_confidence"],
                        "arousal_reason": result["arousal_reason"],
                        "visual_cues": result["visual_cues"],
                        "image_text": result.get("image_text", ""),
                        "request_id": result["request_id"],
                        "api_model": result["model"],
                        "response_content": result["response_content"],
                        "api_raw_json_path": result["raw_json_path"],
                    }
                )
                dump_json(payload, out_path)
                self.logger.info("视觉编码成功: %s", record.slice_id)
        except Exception as exc:
            batch_item_id = self._batch_item_id(records)
            for record, payload, out_path in prepared:
                payload.update(
                    {
                        "status": "failed",
                        "skip_reason": "",
                        "error": str(exc),
                        "api_raw_json_path": self._latest_raw_json_path(
                            self.config.visual_raw_dir,
                            batch_item_id,
                        ),
                    }
                )
                dump_json(payload, out_path)
                self.logger.error("视觉编码失败: %s | %s", record.slice_id, exc)

    def build_slice_output(self, records) -> None:
        rows = []
        for record in records:
            norm_path = self.config.visual_normalized_dir / f"{record.slice_id}.json"
            normalized = load_json(norm_path) if norm_path.exists() else {}
            image_path = Path(record.image_path)
            rows.append(
                {
                    "video_id": record.video_id,
                    "segment_id": self._segment_id(record.segment_index),
                    "image_path": record.image_path,
                    "file_name": image_path.name if record.image_path else "",
                    "start_time": record.start_second,
                    "end_time": record.end_second,
                    "duration_seconds": record.duration_seconds,
                    "visual_label": normalized.get("visual_label", ""),
                    "visual_confidence": normalized.get("visual_confidence", ""),
                    "visual_reason": normalized.get("visual_reason", ""),
                    "arousal_label": normalized.get("arousal_label", ""),
                    "arousal_confidence": normalized.get("arousal_confidence", ""),
                    "arousal_reason": normalized.get("arousal_reason", ""),
                    "visual_cues": json.dumps(
                        normalized.get("visual_cues", []) if isinstance(normalized.get("visual_cues", []), list) else [],
                        ensure_ascii=False,
                    ),
                    "image_text": normalized.get("image_text", ""),
                    "api_model": normalized.get("api_model", ""),
                    "api_raw_json_path": normalized.get("api_raw_json_path")
                    or self._latest_raw_json_path(self.config.visual_raw_dir, record.slice_id),
                    "created_at": normalized.get("created_at", ""),
                    "status": normalized.get("status", self._infer_status(self.config.visual_raw_dir, record.slice_id)),
                    "skip_reason": normalized.get("skip_reason", ""),
                    "error": normalized.get("error", ""),
                    "request_id": normalized.get("request_id", ""),
                    "segments_source_path": record.segments_source_path,
                    "run_name": record.run_name,
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["video_id", "segment_id"]).reset_index(drop=True)
        df = self._order_columns(df)
        write_df(df, self.config.slice_level_visual_csv, self.config.slice_level_visual_parquet)
        self.logger.info("切片级视觉表已写出: %s", self.config.slice_level_visual_csv)
        self.build_video_outputs(df)

    def build_video_outputs(self, slice_df: pd.DataFrame) -> None:
        timeline_blocks = self._build_dual_timeline_blocks(slice_df)
        timeline_summary = self._build_dual_timeline_summary(timeline_blocks)
        write_df(
            timeline_blocks,
            self.config.video_level_dual_timeline_blocks_csv,
            self.config.video_level_dual_timeline_blocks_parquet,
        )
        self.logger.info("视频级双层时间轴分段表已写出: %s", self.config.video_level_dual_timeline_blocks_csv)
        write_df(
            timeline_summary,
            self.config.video_level_dual_timeline_summary_csv,
            self.config.video_level_dual_timeline_summary_parquet,
        )
        self.logger.info("视频级双层时间轴汇总表已写出: %s", self.config.video_level_dual_timeline_summary_csv)

        text_with_ocr = self._build_video_text_with_ocr(slice_df)
        write_df(
            text_with_ocr,
            self.config.video_level_text_with_ocr_csv,
            self.config.video_level_text_with_ocr_parquet,
        )
        self.logger.info("视频级文本融合表已写出: %s", self.config.video_level_text_with_ocr_csv)

    @staticmethod
    def _segment_id(segment_index: int) -> str:
        return f"segment_{int(segment_index):04d}"

    @staticmethod
    def _created_at() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _chunked(records, batch_size: int):
        if batch_size <= 1:
            return [[record] for record in records]
        return [records[index : index + batch_size] for index in range(0, len(records), batch_size)]

    @staticmethod
    def _batch_item_id(records) -> str:
        if len(records) == 1:
            return records[0].slice_id
        return f"batch__{records[0].slice_id}__{records[-1].slice_id}"

    @staticmethod
    def _batch_desc(records) -> str:
        if not records:
            return "EMPTY"
        if len(records) == 1:
            return records[0].slice_id
        return f"{records[0].slice_id}..{records[-1].slice_id}"

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
    def _order_columns(df: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "video_id",
            "segment_id",
            "image_path",
            "file_name",
            "start_time",
            "end_time",
            "duration_seconds",
            "visual_label",
            "visual_confidence",
            "visual_reason",
            "arousal_label",
            "arousal_confidence",
            "arousal_reason",
            "visual_cues",
            "image_text",
            "api_model",
            "api_raw_json_path",
            "created_at",
            "status",
            "skip_reason",
            "error",
            "request_id",
            "segments_source_path",
            "run_name",
        ]
        return df[[col for col in columns if col in df.columns]]

    def _build_dual_timeline_blocks(self, slice_df: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "video_id",
            "block_index",
            "segment_id_start",
            "segment_id_end",
            "start_time",
            "end_time",
            "duration_seconds",
            "slice_count",
            "visual_label",
            "arousal_label",
            "dual_frame",
        ]
        if slice_df.empty:
            return pd.DataFrame(columns=columns)

        success_df = slice_df[slice_df["status"] == "success"].copy()
        if success_df.empty:
            return pd.DataFrame(columns=columns)

        success_df["start_time"] = pd.to_numeric(success_df["start_time"], errors="coerce").fillna(0.0)
        success_df["end_time"] = pd.to_numeric(success_df["end_time"], errors="coerce").fillna(0.0)
        success_df["duration_seconds"] = pd.to_numeric(success_df["duration_seconds"], errors="coerce").fillna(0.0)
        success_df = success_df.sort_values(["video_id", "start_time", "segment_id"]).reset_index(drop=True)

        rows: list[dict[str, Any]] = []
        bridge_tolerance = 0.2

        for video_id, group in success_df.groupby("video_id", dropna=False):
            current: dict[str, Any] | None = None
            block_index = 0
            for row in group.itertuples(index=False):
                visual_label = str(getattr(row, "visual_label", "") or "").strip()
                arousal_label = str(getattr(row, "arousal_label", "") or "").strip()
                start_time = float(getattr(row, "start_time", 0.0) or 0.0)
                end_time = float(getattr(row, "end_time", 0.0) or 0.0)
                duration = float(getattr(row, "duration_seconds", 0.0) or 0.0)
                segment_id = str(getattr(row, "segment_id", "") or "")

                if current is None:
                    current = {
                        "video_id": str(video_id),
                        "block_index": block_index,
                        "segment_id_start": segment_id,
                        "segment_id_end": segment_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration_seconds": duration,
                        "slice_count": 1,
                        "visual_label": visual_label,
                        "arousal_label": arousal_label,
                    }
                    continue

                same_frame = (
                    visual_label == current["visual_label"] and arousal_label == current["arousal_label"]
                )
                is_continuous = start_time <= float(current["end_time"]) + bridge_tolerance
                if same_frame and is_continuous:
                    current["segment_id_end"] = segment_id
                    current["end_time"] = max(float(current["end_time"]), end_time)
                    current["duration_seconds"] = float(current["duration_seconds"]) + duration
                    current["slice_count"] = int(current["slice_count"]) + 1
                else:
                    current["dual_frame"] = f"{current['visual_label']}|{current['arousal_label']}"
                    rows.append(current)
                    block_index += 1
                    current = {
                        "video_id": str(video_id),
                        "block_index": block_index,
                        "segment_id_start": segment_id,
                        "segment_id_end": segment_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration_seconds": duration,
                        "slice_count": 1,
                        "visual_label": visual_label,
                        "arousal_label": arousal_label,
                    }

            if current is not None:
                current["dual_frame"] = f"{current['visual_label']}|{current['arousal_label']}"
                rows.append(current)

        blocks_df = pd.DataFrame(rows)
        if blocks_df.empty:
            return pd.DataFrame(columns=columns)

        for field in ("start_time", "end_time", "duration_seconds"):
            blocks_df[field] = pd.to_numeric(blocks_df[field], errors="coerce").fillna(0.0).round(6)
        blocks_df["slice_count"] = pd.to_numeric(blocks_df["slice_count"], errors="coerce").fillna(0).astype(int)
        blocks_df = blocks_df.sort_values(["video_id", "block_index"]).reset_index(drop=True)
        return blocks_df[[col for col in columns if col in blocks_df.columns]]

    def _build_dual_timeline_summary(self, blocks_df: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "video_id",
            "block_count",
            "slice_count_in_blocks",
            "timeline_start_time",
            "timeline_end_time",
            "total_duration_seconds",
            "main_visual_label",
            "main_visual_share",
            "main_arousal_label",
            "main_arousal_share",
            "main_dual_frame",
            "main_dual_frame_share",
            "visual_share_json",
            "arousal_share_json",
            "dual_frame_share_json",
            "timeline_blocks_json",
            "created_at",
        ]
        if blocks_df.empty:
            return pd.DataFrame(columns=columns)

        rows: list[dict[str, Any]] = []
        for video_id, group in blocks_df.groupby("video_id", dropna=False):
            group = group.sort_values("block_index").reset_index(drop=True)
            total_duration = float(group["duration_seconds"].sum())
            if total_duration <= 0:
                total_duration = 1e-9

            visual_share = (
                group.groupby("visual_label")["duration_seconds"].sum().sort_values(ascending=False) / total_duration
            ).to_dict()
            arousal_share = (
                group.groupby("arousal_label")["duration_seconds"].sum().sort_values(ascending=False) / total_duration
            ).to_dict()
            dual_share = (
                group.groupby("dual_frame")["duration_seconds"].sum().sort_values(ascending=False) / total_duration
            ).to_dict()

            timeline_blocks = [
                {
                    "block_index": int(item.block_index),
                    "segment_id_start": str(item.segment_id_start),
                    "segment_id_end": str(item.segment_id_end),
                    "start_time": round(float(item.start_time), 6),
                    "end_time": round(float(item.end_time), 6),
                    "duration_seconds": round(float(item.duration_seconds), 6),
                    "slice_count": int(item.slice_count),
                    "visual_label": str(item.visual_label),
                    "arousal_label": str(item.arousal_label),
                    "dual_frame": str(item.dual_frame),
                }
                for item in group.itertuples(index=False)
            ]

            main_visual = next(iter(visual_share), "")
            main_arousal = next(iter(arousal_share), "")
            main_dual = next(iter(dual_share), "")
            rows.append(
                {
                    "video_id": str(video_id),
                    "block_count": int(len(group)),
                    "slice_count_in_blocks": int(group["slice_count"].sum()),
                    "timeline_start_time": round(float(group["start_time"].min()), 6),
                    "timeline_end_time": round(float(group["end_time"].max()), 6),
                    "total_duration_seconds": round(float(group["duration_seconds"].sum()), 6),
                    "main_visual_label": main_visual,
                    "main_visual_share": round(float(visual_share.get(main_visual, 0.0)), 6),
                    "main_arousal_label": main_arousal,
                    "main_arousal_share": round(float(arousal_share.get(main_arousal, 0.0)), 6),
                    "main_dual_frame": main_dual,
                    "main_dual_frame_share": round(float(dual_share.get(main_dual, 0.0)), 6),
                    "visual_share_json": json.dumps(
                        {k: round(float(v), 6) for k, v in visual_share.items()},
                        ensure_ascii=False,
                    ),
                    "arousal_share_json": json.dumps(
                        {k: round(float(v), 6) for k, v in arousal_share.items()},
                        ensure_ascii=False,
                    ),
                    "dual_frame_share_json": json.dumps(
                        {k: round(float(v), 6) for k, v in dual_share.items()},
                        ensure_ascii=False,
                    ),
                    "timeline_blocks_json": json.dumps(timeline_blocks, ensure_ascii=False),
                    "created_at": self._created_at(),
                }
            )

        summary_df = pd.DataFrame(rows)
        if not summary_df.empty:
            summary_df = summary_df.sort_values("video_id").reset_index(drop=True)
        return summary_df[[col for col in columns if col in summary_df.columns]]

    def _build_video_text_with_ocr(self, slice_df: pd.DataFrame) -> pd.DataFrame:
        ocr_df = self._aggregate_video_ocr_text(slice_df)
        video_ids = sorted({str(v) for v in slice_df.get("video_id", pd.Series(dtype=str)).dropna().tolist()})
        base_text_df = self._load_base_video_text_table(video_ids)
        merged = base_text_df.merge(ocr_df, on="video_id", how="left")

        for field, default in [
            ("ocr_text_raw_concat", ""),
            ("ocr_text_dedup", ""),
            ("ocr_text_unique_chunk_count", 0),
            ("ocr_text_source_slice_count", 0),
            ("ocr_text_nonempty_slice_count", 0),
            ("ocr_text_coverage_rate", 0.0),
        ]:
            if field not in merged.columns:
                merged[field] = default
            merged[field] = merged[field].fillna(default)

        if "embedded_text" in merged.columns:
            merged["embedded_text_original"] = merged["embedded_text"].fillna("").astype(str)
        else:
            merged["embedded_text_original"] = ""
            merged["embedded_text"] = ""

        merged["embedded_text"] = merged.apply(
            lambda row: self._merge_text_fields(
                row.get("embedded_text_original", ""),
                row.get("ocr_text_dedup", ""),
            ),
            axis=1,
        )
        merged["created_at_visual_ocr_merge"] = self._created_at()
        merged = merged.sort_values("video_id").reset_index(drop=True)
        return merged

    def _aggregate_video_ocr_text(self, slice_df: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "video_id",
            "ocr_text_raw_concat",
            "ocr_text_dedup",
            "ocr_text_unique_chunk_count",
            "ocr_text_source_slice_count",
            "ocr_text_nonempty_slice_count",
            "ocr_text_coverage_rate",
        ]
        if slice_df.empty:
            return pd.DataFrame(columns=columns)

        success_df = slice_df[slice_df["status"] == "success"].copy()
        if success_df.empty:
            return pd.DataFrame(columns=columns)

        success_df["start_time"] = pd.to_numeric(success_df["start_time"], errors="coerce").fillna(0.0)
        success_df = success_df.sort_values(["video_id", "start_time", "segment_id"]).reset_index(drop=True)

        rows: list[dict[str, Any]] = []
        for video_id, group in success_df.groupby("video_id", dropna=False):
            source_count = int(len(group))
            chunks = [self._clean_text_block(text) for text in group["image_text"].astype(str).tolist()]
            chunks = [chunk for chunk in chunks if chunk]
            dedup_chunks = self._dedup_text_chunks(chunks)
            dedup_text = self._dedup_text_by_lines(dedup_chunks)
            nonempty_count = len(chunks)
            rows.append(
                {
                    "video_id": str(video_id),
                    "ocr_text_raw_concat": "\n".join(chunks),
                    "ocr_text_dedup": dedup_text,
                    "ocr_text_unique_chunk_count": int(len(dedup_chunks)),
                    "ocr_text_source_slice_count": source_count,
                    "ocr_text_nonempty_slice_count": nonempty_count,
                    "ocr_text_coverage_rate": round(nonempty_count / source_count, 6) if source_count else 0.0,
                }
            )

        return pd.DataFrame(rows)[columns]

    def _load_base_video_text_table(self, video_ids: list[str]) -> pd.DataFrame:
        base_ids = pd.DataFrame({"video_id": [str(v) for v in video_ids]})
        text_path = self.config.input.video_text_codes_path
        if not text_path:
            return base_ids

        if text_path.suffix.lower() == ".parquet":
            text_df = pd.read_parquet(text_path)
        else:
            text_df = pd.read_csv(text_path, encoding="utf-8-sig")
        if "video_id" not in text_df.columns:
            raise ValueError(f"视频文本表缺少 video_id 列: {text_path}")
        text_df["video_id"] = text_df["video_id"].astype(str)
        text_df = text_df.drop_duplicates(subset=["video_id"], keep="first")
        return base_ids.merge(text_df, on="video_id", how="left")

    def _merge_text_fields(self, existing_text: Any, ocr_text: Any) -> str:
        existing = self._clean_text_block(existing_text)
        ocr = self._clean_text_block(ocr_text)
        if not existing and not ocr:
            return ""
        chunks = []
        if existing:
            chunks.append(existing)
        if ocr:
            chunks.append(ocr)
        return self._dedup_text_by_lines(chunks)

    @staticmethod
    def _clean_text_block(text: Any) -> str:
        value = str(text or "").replace("\u3000", " ").strip()
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value

    def _dedup_text_chunks(self, chunks: list[str]) -> list[str]:
        kept_raw: list[str] = []
        kept_norm: list[str] = []
        for chunk in chunks:
            text = self._clean_text_block(chunk)
            if not text:
                continue
            norm = self._normalize_for_compare(text)
            if not norm:
                continue

            duplicate_index = -1
            for index, existing_norm in enumerate(kept_norm):
                if norm == existing_norm:
                    duplicate_index = index
                    break
                if len(norm) >= 24 and len(existing_norm) >= 24:
                    if norm in existing_norm or existing_norm in norm:
                        duplicate_index = index
                        break
                    if difflib.SequenceMatcher(None, norm, existing_norm).ratio() >= 0.96:
                        duplicate_index = index
                        break

            if duplicate_index == -1:
                kept_raw.append(text)
                kept_norm.append(norm)
                continue

            if len(norm) > len(kept_norm[duplicate_index]):
                kept_norm[duplicate_index] = norm
                kept_raw[duplicate_index] = text
        return kept_raw

    def _dedup_text_by_lines(self, chunks: list[str]) -> str:
        lines: list[str] = []
        for chunk in chunks:
            lines.extend(self._split_nonempty_lines(chunk))
        unique_lines = self._dedup_text_chunks(lines)
        return "\n".join(unique_lines)

    @staticmethod
    def _split_nonempty_lines(text: Any) -> list[str]:
        value = str(text or "")
        parts = re.split(r"[\r\n]+", value)
        return [part.strip() for part in parts if part and part.strip()]

    @staticmethod
    def _normalize_for_compare(text: str) -> str:
        normalized = str(text or "").lower()
        normalized = re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)
        return normalized

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
            eta_seconds = 0
            eta_text = "--:--:--"
            finish_text = "--:--:--"
        else:
            eta_seconds = int((elapsed / done) * remaining)
            eta_text = VisualCodingPipeline._format_seconds(eta_seconds)
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
