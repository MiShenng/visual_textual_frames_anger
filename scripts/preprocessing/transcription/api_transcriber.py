#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional


def build_secure_client_session_factory(original_client_session):
    import aiohttp
    import certifi

    def secure_client_session(*args, **kwargs):
        kwargs.setdefault(
            "connector",
            aiohttp.TCPConnector(
                ssl=ssl.create_default_context(cafile=certifi.where()),
            ),
        )
        return original_client_session(*args, **kwargs)

    return secure_client_session


class APITranscriber:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_websocket_api_url: Optional[str] = None,
        model: Optional[str] = None,
        language: str = "zh",
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        self.base_websocket_api_url = (
            base_websocket_api_url
            or os.environ.get("DASHSCOPE_BASE_WEBSOCKET_API_URL")
            or "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        ).rstrip("/")
        self.model = model or os.environ.get("DASHSCOPE_TRANSCRIBE_MODEL") or "fun-asr-realtime"
        self.language = language
        if not self.api_key:
            raise ValueError("缺少 DASHSCOPE_API_KEY。请通过环境变量提供。")

    def transcribe_audio(
        self,
        audio_path: str,
    ) -> dict[str, Any]:
        import dashscope
        from dashscope.audio.asr import Recognition
        from dashscope.api_entities import websocket_request

        dashscope.base_websocket_api_url = self.base_websocket_api_url
        dashscope.api_key = self.api_key
        audio_format = Path(audio_path).suffix.lstrip(".").lower() or "mp3"
        original_client_session = websocket_request.aiohttp.ClientSession
        websocket_request.aiohttp.ClientSession = build_secure_client_session_factory(original_client_session)

        try:
            recognition = Recognition(
                model=self.model,
                format=audio_format,
                sample_rate=16000,
                callback=None,
            )
            result = recognition.call(audio_path)
        finally:
            websocket_request.aiohttp.ClientSession = original_client_session

        if result.status_code != HTTPStatus.OK:
            message = getattr(result, "message", "") or getattr(result, "code", "")
            raise RuntimeError(f"DashScope 转写任务失败: {message}")

        return self._normalize_result(
            payload=result,
            audio_path=audio_path,
            request_id=result.get_request_id(),
        )

    def save_transcript_bundle(
        self,
        transcript: dict[str, Any],
        output_dir: str,
        video_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        target_dir = Path(output_dir) / video_id
        target_dir.mkdir(parents=True, exist_ok=True)

        json_path = target_dir / f"{video_id}.json"
        txt_path = target_dir / f"{video_id}.txt"
        md_path = target_dir / f"{video_id}.md"

        payload = dict(transcript)
        if metadata:
            payload["metadata"] = metadata

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path.write_text((transcript.get("text") or "").strip() + "\n", encoding="utf-8")
        md_path.write_text(self._to_markdown(transcript, metadata), encoding="utf-8")

        return {
            "json_path": str(json_path),
            "txt_path": str(txt_path),
            "md_path": str(md_path),
        }

    def _normalize_result(
        self,
        payload: Any,
        audio_path: str,
        request_id: str,
    ) -> dict[str, Any]:
        output = getattr(payload, "output", {}) or {}
        sentences = output.get("sentence") or []
        if isinstance(sentences, dict):
            sentences = [sentences]

        combined_texts: list[str] = []
        segments: list[dict[str, Any]] = []

        for sentence in sentences:
            text = (sentence.get("text") or "").strip()
            if text:
                combined_texts.append(text)
            segments.append(
                {
                    "start": round(float(sentence.get("begin_time") or sentence.get("start_time") or 0) / 1000.0, 3),
                    "end": round(float(sentence.get("end_time") or 0) / 1000.0, 3),
                    "text": text,
                    "sentence_id": sentence.get("sentence_id"),
                    "speaker_id": sentence.get("speaker_id"),
                }
            )

        normalized_text = "\n".join(text for text in combined_texts if text).strip()
        if not normalized_text and segments:
            normalized_text = "\n".join(segment["text"] for segment in segments if segment["text"]).strip()

        return {
            "text": normalized_text,
            "segments": segments,
            "audio_path": audio_path,
            "request_id": request_id,
            "raw_result": {
                "status_code": getattr(payload, "status_code", None),
                "request_id": getattr(payload, "request_id", None),
                "code": getattr(payload, "code", None),
                "message": getattr(payload, "message", None),
                "output": output,
                "usage": getattr(payload, "usage", None),
            },
        }

    @staticmethod
    def _to_markdown(transcript: dict[str, Any], metadata: Optional[dict[str, Any]] = None) -> str:
        lines: list[str] = ["# 视频文本提取结果", ""]
        if metadata:
            lines.extend(
                [
                    f"- 视频ID：{metadata.get('platform_video_id', '')}",
                    f"- 作者：{metadata.get('author_name', '')}",
                    f"- 标题：{metadata.get('title', '')}",
                    f"- 发布时间：{metadata.get('published_at', '')}",
                    f"- 匹配关键词：{metadata.get('matched_queries', '')}",
                    "",
                ]
            )

        text = (transcript.get("text") or "").strip()
        lines.extend(["## 全文", "", text, ""])

        if transcript.get("audio_path"):
            lines.extend(["## 音频路径", "", str(transcript["audio_path"]), ""])

        segments = transcript.get("segments") or []
        if segments:
            lines.extend(["## 分段", ""])
            for index, segment in enumerate(segments, start=1):
                start = segment.get("start", "")
                end = segment.get("end", "")
                segment_text = (segment.get("text") or "").strip()
                lines.append(f"{index}. [{start} - {end}] {segment_text}")
            lines.append("")

        raw_result = transcript.get("raw_result")
        if raw_result:
            lines.extend(["## 原始结果", "", "```json", json.dumps(raw_result, ensure_ascii=False, indent=2), "```", ""])

        return "\n".join(lines)
