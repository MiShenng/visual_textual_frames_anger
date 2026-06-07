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
    text_model: str
    request_timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: float
    text_concurrency: int
    enable_thinking: bool | None
    thinking_budget: int | None
    max_completion_tokens: int | None


@dataclass(frozen=True)
class InputConfig:
    reference_csv_path: Path
    transcript_summary_path: Path | None
    ocr_text_table_path: Path | None


@dataclass(frozen=True)
class OutputConfig:
    output_dir: Path
    raw_api_dir: Path
    normalized_dir: Path
    package_dir: Path
    table_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class CodingConfig:
    text_system_prompt: str
    narrative_labels: list[str]
    arousal_labels: list[str]
    confidence_labels: list[str]
    narrative_aliases: dict[str, str]
    arousal_aliases: dict[str, str]
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
    def text_raw_dir(self) -> Path:
        return self.output.raw_api_dir / "text"

    @property
    def text_normalized_dir(self) -> Path:
        return self.output.normalized_dir / "text"

    @property
    def package_json_dir(self) -> Path:
        return self.output.package_dir / "json"

    @property
    def package_txt_dir(self) -> Path:
        return self.output.package_dir / "txt"

    @property
    def package_table_csv(self) -> Path:
        return self.output.table_dir / "video_level_text_material_packages.csv"

    @property
    def package_table_parquet(self) -> Path:
        return self.output.table_dir / "video_level_text_material_packages.parquet"

    @property
    def text_codes_csv(self) -> Path:
        return self.output.table_dir / "video_level_text_frame_codes.csv"

    @property
    def text_codes_parquet(self) -> Path:
        return self.output.table_dir / "video_level_text_frame_codes.parquet"


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


def _resolve_optional_path(value: Any, base_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _resolve_path(text, base_dir)


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


def _normalize_label_list(values: Any, field_name: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{field_name} 必须是数组。")
    labels = [str(v).strip() for v in values if str(v).strip()]
    if not labels:
        raise ValueError(f"{field_name} 不能为空。")
    return labels


def _normalize_alias_map(values: Any) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("别名配置必须是对象。")
    result: dict[str, str] = {}
    for key, value in values.items():
        k = str(key).strip().replace(" ", "").replace("　", "")
        v = str(value).strip().replace(" ", "").replace("　", "")
        if k and v:
            result[k] = v
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
        str(coding_data.get("text_system_prompt_path", "prompts/text_system_prompt.txt")),
        config_path.parent,
    )
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    text_system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not text_system_prompt:
        raise ValueError("提示词内容为空。")

    output_dir = _resolve_path(str(output_data.get("output_dir", "output")), config_path.parent)
    output = OutputConfig(
        output_dir=output_dir,
        raw_api_dir=output_dir / "raw_api",
        normalized_dir=output_dir / "normalized",
        package_dir=output_dir / "text_material_packages",
        table_dir=output_dir / "tables",
        log_dir=output_dir / "logs",
    )
    for path in [
        output.output_dir,
        output.raw_api_dir,
        output.normalized_dir,
        output.package_dir,
        output.table_dir,
        output.log_dir,
        output.raw_api_dir / "text",
        output.normalized_dir / "text",
        output.package_dir / "json",
        output.package_dir / "txt",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    config = AppConfig(
        api=ApiConfig(
            api_key=api_key,
            api_url=str(api_data.get("api_url", "")).strip(),
            text_model=str(api_data.get("text_model", "")).strip(),
            request_timeout_seconds=int(api_data.get("request_timeout_seconds", 120)),
            max_retries=int(api_data.get("max_retries", 5)),
            retry_backoff_seconds=float(api_data.get("retry_backoff_seconds", 3.0)),
            text_concurrency=int(api_data.get("text_concurrency", 8)),
            enable_thinking=_normalize_optional_bool(api_data.get("enable_thinking", False)),
            thinking_budget=_normalize_optional_int(api_data.get("thinking_budget")),
            max_completion_tokens=_normalize_optional_int(api_data.get("max_completion_tokens")),
        ),
        input=InputConfig(
            reference_csv_path=_resolve_path(str(input_data.get("reference_csv_path", "")), config_path.parent),
            transcript_summary_path=_resolve_optional_path(input_data.get("transcript_summary_path"), config_path.parent),
            ocr_text_table_path=_resolve_optional_path(input_data.get("ocr_text_table_path"), config_path.parent),
        ),
        output=output,
        coding=CodingConfig(
            text_system_prompt=text_system_prompt,
            narrative_labels=_normalize_label_list(coding_data.get("narrative_labels", []), "coding.narrative_labels"),
            arousal_labels=_normalize_label_list(coding_data.get("arousal_labels", []), "coding.arousal_labels"),
            confidence_labels=_normalize_label_list(coding_data.get("confidence_labels", []), "coding.confidence_labels"),
            narrative_aliases=_normalize_alias_map(coding_data.get("narrative_aliases")),
            arousal_aliases=_normalize_alias_map(coding_data.get("arousal_aliases")),
            confidence_aliases=_normalize_alias_map(coding_data.get("confidence_aliases")),
        ),
        pipeline=PipelineConfig(
            overwrite_existing=bool(pipeline_data.get("overwrite_existing", False)),
        ),
    )

    if not config.api.api_url:
        raise ValueError("api.api_url 不能为空。")
    if not config.api.text_model:
        raise ValueError("api.text_model 不能为空。")
    if not config.input.reference_csv_path.exists():
        raise FileNotFoundError(f"reference 文件不存在: {config.input.reference_csv_path}")
    if config.input.transcript_summary_path and not config.input.transcript_summary_path.exists():
        raise FileNotFoundError(f"转录汇总文件不存在: {config.input.transcript_summary_path}")
    if config.input.ocr_text_table_path and not config.input.ocr_text_table_path.exists():
        raise FileNotFoundError(f"OCR 文本表不存在: {config.input.ocr_text_table_path}")

    return config

