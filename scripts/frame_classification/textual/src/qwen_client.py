from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from json_repair import repair_json
from openai import OpenAI

from .prompts import build_text_prompt, normalize_label


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

    def code_text(self, item: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self.config.coding.text_system_prompt},
            {"role": "user", "content": build_text_prompt(item)},
        ]
        parsed, meta = self._request_json(
            messages=messages,
            item_id=item["video_id"],
            raw_dir=raw_dir,
            preview={"video_id": item["video_id"]},
        )
        return {
            "narrative_label": normalize_label(
                parsed.get("narrative_label"),
                self.config.coding.narrative_labels,
                self.config.coding.narrative_aliases,
            ),
            "narrative_confidence": self._normalize_confidence(parsed.get("narrative_confidence")),
            "narrative_reason": str(parsed.get("narrative_reason", "") or "").strip(),
            "arousal_label": normalize_label(
                parsed.get("arousal_label"),
                self.config.coding.arousal_labels,
                self.config.coding.arousal_aliases,
            ),
            "arousal_confidence": self._normalize_confidence(parsed.get("arousal_confidence")),
            "arousal_reason": str(parsed.get("arousal_reason", "") or "").strip(),
            "narrative_cues": self._normalize_cues(parsed.get("narrative_cues")),
            "request_id": meta.get("request_id", ""),
            "model": self.config.api.text_model,
            "response_content": meta.get("content", ""),
            "raw_json_path": meta.get("raw_json_path", ""),
        }

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
                    "model": self.config.api.text_model,
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
            "model": self.config.api.text_model,
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
        start_obj = content.find("{")
        end_obj = content.rfind("}")
        if start_obj != -1 and end_obj > start_obj:
            candidates.append(content[start_obj : end_obj + 1])

        for candidate in candidates:
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                pass

        repaired = repair_json(content, return_objects=True)
        if not isinstance(repaired, dict):
            raise ValueError(f"无法修复为 JSON 对象: {content[:200]}")
        return repaired

    def _normalize_confidence(self, value: Any) -> str:
        fallback = "low" if "low" in self.config.coding.confidence_labels else self.config.coding.confidence_labels[0]
        text = str(value or "").strip()
        if not text:
            return fallback
        try:
            return normalize_label(
                text,
                self.config.coding.confidence_labels,
                self.config.coding.confidence_aliases,
            )
        except Exception:
            return fallback

    @staticmethod
    def _normalize_cues(value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("narrative_cues 必须是数组。")
        cues: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                cues.append(text)
        return cues[:3]

