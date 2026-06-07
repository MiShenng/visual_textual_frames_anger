from __future__ import annotations

import base64
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from json_repair import repair_json
from openai import OpenAI
from PIL import Image

from .prompts import build_visual_batch_prompt, normalize_label


class QwenClient:
    def __init__(self, config, logger) -> None:
        self.config = config
        self.logger = logger
        self.timeout = config.api.request_timeout_seconds
        self.client = OpenAI(
            api_key=config.api.api_key,
            base_url=config.api.api_url,
            max_retries=0,
            http_client=httpx.Client(
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=True,
            ),
        )

    def code_visual_batch(self, items: list[dict[str, Any]], raw_dir: Path) -> list[dict[str, Any]]:
        if not items:
            return []

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": build_visual_batch_prompt(
                    items=items,
                    visual_labels=self.config.coding.visual_labels,
                    arousal_labels=self.config.coding.arousal_labels,
                    confidence_labels=self.config.coding.confidence_labels,
                ),
            }
        ]
        for index, item in enumerate(items, start=1):
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"第{index}张图\n"
                        f"slice_id: {item['slice_id']}"
                    ),
                }
            )
            data_url = self._image_to_data_url(
                path=Path(item["image_path"]),
                max_side=self.config.api.visual_max_image_side,
                jpeg_quality=self.config.api.visual_jpeg_quality,
            )
            content.append({"type": "image_url", "image_url": {"url": data_url}})

        messages = [
            {"role": "system", "content": self.config.coding.visual_system_prompt},
            {"role": "user", "content": content},
        ]
        parsed, meta = self._request_json(
            messages=messages,
            item_id=self._batch_item_id(items),
            raw_dir=raw_dir,
            preview={"batch_size": len(items), "slice_ids": [item["slice_id"] for item in items]},
        )
        parsed_items = self._coerce_batch_items(parsed)
        parsed_by_id = {
            str(item.get("slice_id", "")).strip(): item
            for item in parsed_items
            if isinstance(item, dict) and str(item.get("slice_id", "")).strip()
        }

        results: list[dict[str, Any]] = []
        for item in items:
            slice_id = item["slice_id"]
            entry = parsed_by_id.get(slice_id)
            if not entry:
                raise ValueError(f"批量返回缺少 slice_id: {slice_id}")
            results.append(
                {
                    "slice_id": slice_id,
                    "visual_label": normalize_label(
                        entry.get("visual_label"),
                        self.config.coding.visual_labels,
                        self.config.coding.visual_label_aliases,
                    ),
                    "visual_confidence": self._normalize_confidence(
                        entry.get("visual_confidence"),
                        field_name="visual_confidence",
                        slice_id=slice_id,
                    ),
                    "visual_reason": str(entry.get("visual_reason", "") or "").strip(),
                    "arousal_label": normalize_label(
                        entry.get("arousal_label"),
                        self.config.coding.arousal_labels,
                        self.config.coding.arousal_label_aliases,
                    ),
                    "arousal_confidence": self._normalize_confidence(
                        entry.get("arousal_confidence"),
                        field_name="arousal_confidence",
                        slice_id=slice_id,
                    ),
                    "arousal_reason": str(entry.get("arousal_reason", "") or "").strip(),
                    "visual_cues": self._normalize_visual_cues(entry.get("visual_cues")),
                    "image_text": str(entry.get("image_text", "") or "").strip(),
                    "request_id": meta.get("request_id", ""),
                    "model": self.config.api.visual_model,
                    "response_content": meta.get("content", ""),
                    "raw_json_path": meta.get("raw_json_path", ""),
                }
            )
        return results

    def _request_json(
        self,
        messages: list[dict[str, Any]],
        item_id: str,
        raw_dir: Path,
        preview: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.api.max_retries + 1):
            response_json: dict[str, Any] | None = None
            attempt_path: Path | None = None
            try:
                request_kwargs: dict[str, Any] = {
                    "model": self.config.api.visual_model,
                    "messages": messages,
                    "temperature": 0,
                    "top_p": 0.1,
                }
                if self.config.api.max_completion_tokens:
                    request_kwargs["max_tokens"] = self.config.api.max_completion_tokens
                extra_body: dict[str, Any] = {}
                if self.config.api.enable_thinking is not None:
                    extra_body["enable_thinking"] = self.config.api.enable_thinking
                if self.config.api.thinking_budget is not None:
                    extra_body["thinking_budget"] = self.config.api.thinking_budget
                if extra_body:
                    request_kwargs["extra_body"] = extra_body

                completion = self.client.with_options(timeout=self.timeout).chat.completions.create(**request_kwargs)
                response_json = completion.model_dump(mode="json")
                attempt_path = self._save_attempt(
                    raw_dir=raw_dir,
                    item_id=item_id,
                    attempt=attempt,
                    preview=preview,
                    response_json=response_json,
                    response_text=json.dumps(response_json, ensure_ascii=False),
                    error=None,
                )
                content = self._extract_content(response_json)
                parsed = self._parse_json_text(content)
                return parsed, {
                    "request_id": str(response_json.get("id", "")),
                    "content": content,
                    "raw_json_path": str(attempt_path) if attempt_path else "",
                }
            except Exception as exc:
                last_error = exc
                attempt_path = self._save_attempt(
                    raw_dir=raw_dir,
                    item_id=item_id,
                    attempt=attempt,
                    preview=preview,
                    response_json=response_json,
                    response_text=json.dumps(response_json, ensure_ascii=False) if response_json else "",
                    error=str(exc),
                )
                self.logger.warning(
                    "API 请求失败 | item=%s | attempt=%s/%s | %s | raw=%s",
                    item_id,
                    attempt,
                    self.config.api.max_retries,
                    exc,
                    attempt_path,
                )
                time.sleep(self.config.api.retry_backoff_seconds * attempt)
        raise RuntimeError(f"多次重试后仍失败: {item_id}") from last_error

    def _save_attempt(
        self,
        raw_dir: Path,
        item_id: str,
        attempt: int,
        preview: dict[str, Any],
        response_json: dict[str, Any] | None,
        response_text: str,
        error: str | None,
    ) -> Path:
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{item_id}__attempt_{attempt:02d}.json"
        payload = {
            "item_id": item_id,
            "attempt": attempt,
            "model": self.config.api.visual_model,
            "preview": preview,
            "response_json": response_json,
            "response_text": response_text,
            "error": error,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _extract_content(response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        if not choices:
            raise ValueError("API 返回缺少 choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "\n".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _parse_json_text(content: str) -> Any:
        if not content:
            raise ValueError("模型返回空内容")
        candidates = [content]
        start_array = content.find("[")
        end_array = content.rfind("]")
        if start_array != -1 and end_array > start_array:
            candidates.append(content[start_array : end_array + 1])
        start_obj = content.find("{")
        end_obj = content.rfind("}")
        if start_obj != -1 and end_obj > start_obj:
            candidates.append(content[start_obj : end_obj + 1])

        for candidate in candidates:
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, (list, dict)):
                    return loaded
            except Exception:
                pass

        repaired = repair_json(content, return_objects=True)
        if not isinstance(repaired, (list, dict)):
            raise ValueError(f"无法修复为 JSON: {content[:200]}")
        return repaired

    @staticmethod
    def _coerce_batch_items(parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            for key in ("items", "results", "data"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise ValueError("批量视觉响应不是 JSON 数组。")

    @staticmethod
    def _normalize_visual_cues(value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("visual_cues 必须是数组。")
        cues: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                cues.append(text)
        return cues[:3]

    def _normalize_confidence(self, value: Any, field_name: str, slice_id: str) -> str:
        fallback = "low" if "low" in self.config.coding.confidence_labels else self.config.coding.confidence_labels[0]
        text = str(value or "").strip()
        if not text:
            self.logger.warning("%s 为空，已回填 %s | slice_id=%s", field_name, fallback, slice_id)
            return fallback
        try:
            return normalize_label(
                text,
                self.config.coding.confidence_labels,
                self.config.coding.confidence_aliases,
            )
        except Exception:
            self.logger.warning("%s 非法，已回填 %s | slice_id=%s | value=%s", field_name, fallback, slice_id, text)
            return fallback

    @staticmethod
    def _batch_item_id(items: list[dict[str, Any]]) -> str:
        if len(items) == 1:
            return items[0]["slice_id"]
        return f"batch__{items[0]['slice_id']}__{items[-1]['slice_id']}"

    @staticmethod
    def _image_to_data_url(path: Path, max_side: int, jpeg_quality: int) -> str:
        with Image.open(path) as image:
            working = image.convert("RGB")
            if max(working.size) > max_side:
                working.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            working.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
