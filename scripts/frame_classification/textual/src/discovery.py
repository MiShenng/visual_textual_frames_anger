from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TextRecord:
    video_id: str
    title: str
    author_name: str
    publish_time: str
    title_text: str
    transcript_text: str
    subtitle_text: str
    ocr_text: str
    text_material: str
    source_reference_path: str
    source_transcript_path: str
    source_ocr_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_text_records(reference_path: Path, transcript_path: Path | None, ocr_path: Path | None, logger) -> list[TextRecord]:
    ref = _load_reference_df(reference_path)
    transcript = _load_transcript_df(transcript_path) if transcript_path else pd.DataFrame(columns=["video_id"])
    ocr = _load_ocr_df(ocr_path) if ocr_path else pd.DataFrame(columns=["video_id"])

    transcript_ids = set(transcript.get("video_id", []))
    ocr_ids = set(ocr.get("video_id", []))
    ref_ids = set(ref["video_id"])

    # Sample scope:
    # 1) Prefer transcript universe (研究主样本 480)
    # 2) Fallback to OCR universe
    # 3) Fallback to reference universe
    if transcript_ids:
        ids = sorted(transcript_ids)
        scope = "transcript"
    elif ocr_ids:
        ids = sorted(ocr_ids)
        scope = "ocr"
    else:
        ids = sorted(ref_ids)
        scope = "reference"

    base = pd.DataFrame({"video_id": ids})
    merged = (
        base.merge(ref, on="video_id", how="left", suffixes=("", "_ref"))
        .merge(transcript, on="video_id", how="left", suffixes=("", "_transcript"))
        .merge(ocr, on="video_id", how="left", suffixes=("", "_ocr"))
    )

    records: list[TextRecord] = []
    for row in merged.to_dict(orient="records"):
        title = _first_nonempty(row.get("title"), row.get("title_transcript"), row.get("title_text"))
        author_name = _first_nonempty(row.get("author_name"), row.get("author_name_transcript"))
        publish_time = _first_nonempty(row.get("publish_time"), row.get("published_at"), row.get("published_at_transcript"))
        title_text = _first_nonempty(row.get("title_text"), title)
        transcript_text = _first_nonempty(row.get("transcript_text_transcript"), row.get("transcript_text"))
        subtitle_text = _first_nonempty(row.get("subtitle_text"), row.get("subtitle_text_ocr"))
        ocr_text = _first_nonempty(row.get("ocr_text_dedup"), row.get("image_text_merged"), row.get("overlay_text"))

        text_material = _compose_text_material(
            title=title,
            title_text=title_text,
            transcript_text=transcript_text,
            subtitle_text=subtitle_text,
            ocr_text=ocr_text,
        )

        records.append(
            TextRecord(
                video_id=str(row.get("video_id", "")),
                title=title,
                author_name=author_name,
                publish_time=publish_time,
                title_text=title_text,
                transcript_text=transcript_text,
                subtitle_text=subtitle_text,
                ocr_text=ocr_text,
                text_material=text_material,
                source_reference_path=str(reference_path),
                source_transcript_path=str(transcript_path) if transcript_path else "",
                source_ocr_path=str(ocr_path) if ocr_path else "",
            )
        )

    logger.info(
        "文本材料发现完成：reference=%s, transcript=%s, ocr=%s, scope=%s, merged_video=%s",
        len(ref),
        len(transcript),
        len(ocr),
        scope,
        len(records),
    )
    return records


def _load_reference_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "video_id" not in df.columns:
        raise ValueError(f"reference 缺少 video_id 列: {path}")
    keep = [
        "video_id",
        "title",
        "author_name",
        "publish_time",
        "title_text",
        "transcript_text",
        "subtitle_text",
        "overlay_text",
        "image_text_merged",
        "text_package",
    ]
    out = df[[col for col in keep if col in df.columns]].copy()
    out["video_id"] = out["video_id"].map(_normalize_video_id)
    for col in out.columns:
        if col != "video_id":
            out[col] = out[col].map(_clean_text)
    out = out.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)
    return out


def _load_transcript_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    video_col = "platform_video_id" if "platform_video_id" in df.columns else "video_id"
    if video_col not in df.columns:
        raise ValueError(f"转录表缺少视频ID列: {path}")
    out = pd.DataFrame(
        {
            "video_id": df[video_col].map(_normalize_video_id),
            "title_transcript": df.get("title", "").map(_clean_text) if "title" in df.columns else "",
            "author_name_transcript": df.get("author_name", "").map(_clean_text) if "author_name" in df.columns else "",
            "published_at_transcript": df.get("published_at", "").map(_clean_text) if "published_at" in df.columns else "",
            "transcript_text_transcript": df.get("transcript_text", "").map(_clean_text) if "transcript_text" in df.columns else "",
            "json_path_transcript": df.get("json_path", "").map(_clean_text) if "json_path" in df.columns else "",
        }
    )
    out = out.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)
    return out


def _load_ocr_df(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
    if "video_id" not in df.columns:
        raise ValueError(f"OCR 表缺少 video_id 列: {path}")
    out = pd.DataFrame(
        {
            "video_id": df["video_id"].map(_normalize_video_id),
            "ocr_text_dedup": df.get("ocr_text_dedup", "").map(_clean_text) if "ocr_text_dedup" in df.columns else "",
            "subtitle_text_ocr": df.get("subtitle_text", "").map(_clean_text) if "subtitle_text" in df.columns else "",
            "embedded_text_ocr": df.get("embedded_text", "").map(_clean_text) if "embedded_text" in df.columns else "",
        }
    )
    out = out.drop_duplicates(subset=["video_id"], keep="first").reset_index(drop=True)
    return out


def _compose_text_material(
    title: str,
    title_text: str,
    transcript_text: str,
    subtitle_text: str,
    ocr_text: str,
) -> str:
    sections: list[tuple[str, str]] = []
    seen_norm: set[str] = set()

    for label, content in [
        ("标题", title),
        ("标题文本", title_text),
        ("语音转录", transcript_text),
        ("字幕", subtitle_text),
        ("图片文字/OCR", ocr_text),
    ]:
        cleaned = _clean_text(content)
        if not cleaned:
            continue
        deduped = _dedup_text_by_lines(cleaned)
        norm = _normalize_for_compare(deduped)
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        sections.append((label, deduped))

    if not sections:
        return ""
    return "\n\n".join(f"【{label}】\n{text}" for label, text in sections).strip()


def _dedup_text_by_lines(text: str) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line and line.strip()]
    kept: list[str] = []
    kept_norm: list[str] = []
    for line in lines:
        norm = _normalize_for_compare(line)
        if not norm:
            continue
        duplicate = False
        for old in kept_norm:
            if norm == old:
                duplicate = True
                break
            if len(norm) >= 24 and len(old) >= 24 and (norm in old or old in norm):
                duplicate = True
                break
        if not duplicate:
            kept.append(line)
            kept_norm.append(norm)
    return "\n".join(kept)


def _normalize_video_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\u3000", " ").strip()
    if text.lower() in {"nan", "none"}:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_for_compare(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)
    return normalized


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""
