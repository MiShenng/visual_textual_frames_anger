from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


@dataclass(frozen=True)
class ApiConfig:
    api_key: str
    api_url: str
    visual_model: str
    request_timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: float
    visual_concurrency: int
    visual_batch_size: int
    visual_max_image_side: int
    visual_jpeg_quality: int
    enable_thinking: bool | None
    thinking_budget: int | None
    max_completion_tokens: int | None


@dataclass(frozen=True)
class InputConfig:
    slice_results_dir: Path
    video_text_codes_path: Path | None


@dataclass(frozen=True)
class OutputConfig:
    output_dir: Path
    raw_api_dir: Path
    normalized_dir: Path
    table_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class CodingConfig:
    visual_system_prompt: str
    visual_labels: list[str]
    arousal_labels: list[str]
    confidence_labels: list[str]
    visual_label_aliases: dict[str, str]
    arousal_label_aliases: dict[str, str]
    confidence_aliases: dict[str, str]


@dataclass(frozen=True)
class PipelineConfig:
    overwrite_existing: bool


@dataclass(frozen=True)
class AppConfig:
    api: ApiConfig
    input: InputConfig
    output: OutputConfig
    coding: CodingConfig
    pipeline: PipelineConfig

    @property
    def visual_raw_dir(self) -> Path:
        return self.output.raw_api_dir / "visual"

    @property
    def visual_normalized_dir(self) -> Path:
        return self.output.normalized_dir / "visual"

    @property
    def slice_level_visual_csv(self) -> Path:
        return self.output.table_dir / "slice_level_visual_codes.csv"

    @property
    def slice_level_visual_parquet(self) -> Path:
        return self.output.table_dir / "slice_level_visual_codes.parquet"

    @property
    def video_level_text_with_ocr_csv(self) -> Path:
        return self.output.table_dir / "video_level_text_codes_with_ocr.csv"

    @property
    def video_level_text_with_ocr_parquet(self) -> Path:
        return self.output.table_dir / "video_level_text_codes_with_ocr.parquet"

    @property
    def video_level_dual_timeline_blocks_csv(self) -> Path:
        return self.output.table_dir / "video_level_dual_timeline_blocks.csv"

    @property
    def video_level_dual_timeline_blocks_parquet(self) -> Path:
        return self.output.table_dir / "video_level_dual_timeline_blocks.parquet"

    @property
    def video_level_dual_timeline_summary_csv(self) -> Path:
        return self.output.table_dir / "video_level_dual_timeline_summary.csv"

    @property
    def video_level_dual_timeline_summary_parquet(self) -> Path:
        return self.output.table_dir / "video_level_dual_timeline_summary.parquet"


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda m: os.getenv(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


def _resolve_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _normalize_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"布尔配置非法: {value}")


def _normalize_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number <= 0:
        return None
    return number


def _resolve_optional_path(value: Any, base_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _resolve_path(text, base_dir)


def _normalize_label_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("类目配置必须是数组。")
    labels = [str(v).strip() for v in values if str(v).strip()]
    if not labels:
        raise ValueError("类目配置不能为空。")
    return labels


def _normalize_alias_map(values: Any) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("别名配置必须是对象。")
    result: dict[str, str] = {}
    for k, v in values.items():
        key = str(k).strip().replace(" ", "").replace("　", "")
        val = str(v).strip().replace(" ", "").replace("　", "")
        if key and val:
            result[key] = val
    return result


def load_config(config_path: Path, require_api_key: bool = True) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    load_dotenv(config_path.parent / ".env")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    data = _expand_env(raw)

    api_data = data.get("api", {})
    input_data = data.get("input", {})
    output_data = data.get("output", {})
    coding_data = data.get("coding", {})
    pipeline_data = data.get("pipeline", {})

    api_key = str(api_data.get("api_key", "")).strip()
    if not api_key or api_key.startswith("${"):
        api_key = os.getenv("QWEN_API_KEY", "").strip()
    if require_api_key and not api_key:
        raise ValueError("未配置 QWEN_API_KEY。请在 .env 或 config.yaml 配置。")

    prompt_path = _resolve_path(
        str(coding_data.get("visual_system_prompt_path", "prompts/visual_system_prompt.txt")),
        config_path.parent,
    )
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    visual_system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not visual_system_prompt:
        raise ValueError("提示词文件内容为空。")

    output_dir = _resolve_path(str(output_data.get("output_dir", "output")), config_path.parent)
    output = OutputConfig(
        output_dir=output_dir,
        raw_api_dir=output_dir / "raw_api",
        normalized_dir=output_dir / "normalized",
        table_dir=output_dir / "tables",
        log_dir=output_dir / "logs",
    )
    for path in [
        output.output_dir,
        output.raw_api_dir,
        output.normalized_dir,
        output.table_dir,
        output.log_dir,
        output.raw_api_dir / "visual",
        output.normalized_dir / "visual",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    config = AppConfig(
        api=ApiConfig(
            api_key=api_key,
            api_url=str(api_data.get("api_url", "")).strip(),
            visual_model=str(api_data.get("visual_model", "")).strip(),
            request_timeout_seconds=int(api_data.get("request_timeout_seconds", 120)),
            max_retries=int(api_data.get("max_retries", 5)),
            retry_backoff_seconds=float(api_data.get("retry_backoff_seconds", 3.0)),
            visual_concurrency=int(api_data.get("visual_concurrency", 8)),
            visual_batch_size=int(api_data.get("visual_batch_size", 4)),
            visual_max_image_side=int(api_data.get("visual_max_image_side", 960)),
            visual_jpeg_quality=int(api_data.get("visual_jpeg_quality", 85)),
            enable_thinking=_normalize_optional_bool(api_data.get("enable_thinking", False)),
            thinking_budget=_normalize_optional_int(api_data.get("thinking_budget")),
            max_completion_tokens=_normalize_optional_int(api_data.get("max_completion_tokens")),
        ),
        input=InputConfig(
            slice_results_dir=_resolve_path(str(input_data.get("slice_results_dir", ".")), config_path.parent),
            video_text_codes_path=_resolve_optional_path(input_data.get("video_text_codes_path"), config_path.parent),
        ),
        output=output,
        coding=CodingConfig(
            visual_system_prompt=visual_system_prompt,
            visual_labels=_normalize_label_list(coding_data.get("visual_labels", [])),
            arousal_labels=_normalize_label_list(coding_data.get("arousal_labels", [])),
            confidence_labels=_normalize_label_list(coding_data.get("confidence_labels", [])),
            visual_label_aliases=_normalize_alias_map(coding_data.get("visual_label_aliases")),
            arousal_label_aliases=_normalize_alias_map(coding_data.get("arousal_label_aliases")),
            confidence_aliases=_normalize_alias_map(coding_data.get("confidence_aliases")),
        ),
        pipeline=PipelineConfig(
            overwrite_existing=bool(pipeline_data.get("overwrite_existing", False)),
        ),
    )

    if not config.api.api_url:
        raise ValueError("api.api_url 不能为空。")
    if not config.api.visual_model:
        raise ValueError("api.visual_model 不能为空。")
    if not config.input.slice_results_dir.exists():
        raise FileNotFoundError(f"切片目录不存在: {config.input.slice_results_dir}")
    if config.api.visual_batch_size <= 0:
        raise ValueError("api.visual_batch_size 必须大于 0。")
    if config.api.visual_concurrency <= 0:
        raise ValueError("api.visual_concurrency 必须大于 0。")
    if config.input.video_text_codes_path and not config.input.video_text_codes_path.exists():
        raise FileNotFoundError(f"视频文本表不存在: {config.input.video_text_codes_path}")

    return config
