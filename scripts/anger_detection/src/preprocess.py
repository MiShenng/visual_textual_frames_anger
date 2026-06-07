#!/usr/bin/env python3
"""Preprocess raw Chinese social media text into a unified master parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

STANDARD_COLUMNS = [
    "id",
    "raw_text",
    "clean_text",
    "time",
    "post_id",
    "video_id",
    "user_id",
    "parent_id",
    "likes",
]

COLUMN_CANDIDATES: Dict[str, List[str]] = {
    "id": ["id", "ID", "comment_id", "cid", "note_id", "msg_id"],
    "raw_text": [
        "raw_text",
        "text",
        "content",
        "comment",
        "评论",
        "评论内容",
        "正文",
        "message",
    ],
    "time": ["time", "created_at", "create_time", "timestamp", "发布时间", "日期"],
    "post_id": ["post_id", "postid", "帖子id", "note_id", "aweme_id"],
    "video_id": ["video_id", "videoid", "视频id", "item_id", "aweme_id"],
    "user_id": ["user_id", "userid", "uid", "作者id", "用户id"],
    "parent_id": ["parent_id", "reply_to", "root_id", "上级评论id"],
    "likes": ["likes", "like_count", "点赞", "点赞数", "upvotes"],
}

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预处理原始社交媒体文本数据")
    parser.add_argument("--input-dir", default="data/raw", help="原始数据目录（csv/xls/xlsx）")
    parser.add_argument("--output-path", default="data/processed/master.parquet", help="主数据输出路径")
    parser.add_argument(
        "--report-path",
        default="outputs/logs/preprocess_report.json",
        help="预处理报告输出路径",
    )
    parser.add_argument(
        "--create-mock-if-missing",
        action="store_true",
        help="若 input-dir 无原始文件，自动生成 mock 数据后继续",
    )
    return parser.parse_args()


def normalize_col_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(name)).lower()


def find_data_files(input_dir: Path) -> List[Path]:
    files = []
    for pattern in ("*.csv", "*.xlsx", "*.xls"):
        files.extend(sorted(input_dir.glob(pattern)))
    return files


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    last_err: Optional[Exception] = None
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise ValueError(f"读取 CSV 失败: {path} | 最后错误: {last_err}")


def read_source_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_with_fallback(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件类型: {path}")


def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    norm_to_original = {normalize_col_name(col): col for col in df.columns}
    for cand in candidates:
        key = normalize_col_name(cand)
        if key in norm_to_original:
            return norm_to_original[key]
    return None


def guess_text_column(df: pd.DataFrame) -> Optional[str]:
    object_like = [c for c in df.columns if df[c].dtype == "object"]
    if not object_like:
        return None
    # Pick column with max non-empty string ratio.
    best_col = None
    best_score = -1.0
    for col in object_like:
        series = df[col].fillna("").astype(str).str.strip()
        score = (series != "").mean()
        if score > best_score:
            best_score = score
            best_col = col
    return best_col


def create_mock_raw_data(input_dir: Path) -> Path:
    input_dir.mkdir(parents=True, exist_ok=True)
    mock_path = input_dir / "mock_raw.csv"
    mock_df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, 6],
            "content": [
                "真是气死我了，这也太离谱了！",
                "今天有点难过。",
                "[笑哭][笑哭]",
                "这个功能一般般。",
                "你们必须给个说法！",
                "   ",
            ],
            "time": [
                "2026-03-01 12:00:00",
                "2026-03-01 12:05:00",
                "2026-03-01 12:10:00",
                "2026-03-02 08:00:00",
                "2026-03-02 08:30:00",
                "2026-03-02 09:00:00",
            ],
            "video_id": ["v1", "v1", "v2", "v2", "v3", "v3"],
            "user_id": ["u1", "u2", "u3", "u4", "u5", "u6"],
            "likes": [10, 2, 0, 1, 5, 0],
        }
    )
    mock_df.to_csv(mock_path, index=False, encoding="utf-8-sig")
    return mock_path


def is_emoji_char(ch: str) -> bool:
    codepoint = ord(ch)
    emoji_ranges = [
        (0x1F300, 0x1F5FF),
        (0x1F600, 0x1F64F),
        (0x1F680, 0x1F6FF),
        (0x1F900, 0x1F9FF),
        (0x1FA70, 0x1FAFF),
        (0x2600, 0x26FF),
        (0x2700, 0x27BF),
    ]
    return any(start <= codepoint <= end for start, end in emoji_ranges)


def is_only_emoji_or_symbol(text: str) -> bool:
    s = str(text).strip()
    if not s:
        return True

    for ch in s:
        if ch.isspace():
            continue
        if ch.isalnum() or CJK_PATTERN.search(ch):
            return False
        category = unicodedata.category(ch)
        if category.startswith(("P", "S")) or is_emoji_char(ch):
            continue
        return False
    return True


def clean_text(text: str) -> str:
    s = str(text)
    s = s.replace("\ufeff", "").replace("\u200b", "").replace("\u200d", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def generate_stable_id(source_name: str, row_idx: int, text: str) -> str:
    payload = f"{source_name}::{row_idx}::{text}".encode("utf-8", errors="ignore")
    return hashlib.md5(payload).hexdigest()[:16]


def map_and_unify(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    mapped: Dict[str, Optional[str]] = {}
    for target_col, candidates in COLUMN_CANDIDATES.items():
        mapped[target_col] = find_column(df, candidates)

    if mapped["raw_text"] is None:
        guessed = guess_text_column(df)
        if guessed is None:
            raise ValueError(f"文件 {source_name} 无法识别文本列，请检查源数据列名")
        mapped["raw_text"] = guessed

    out = pd.DataFrame(index=df.index)
    for col in STANDARD_COLUMNS:
        if col == "clean_text":
            continue
        src_col = mapped.get(col)
        out[col] = df[src_col] if src_col is not None else pd.NA

    if mapped.get("id") is None:
        out["id"] = [
            generate_stable_id(source_name=source_name, row_idx=i, text=str(t))
            for i, t in enumerate(out["raw_text"].fillna(""), start=1)
        ]

    out["clean_text"] = out["raw_text"].fillna("").astype(str).map(clean_text)
    out["likes"] = pd.to_numeric(out["likes"], errors="coerce")

    return out[STANDARD_COLUMNS]


def preprocess_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, int]]:
    report_counts: Dict[str, int] = {}
    report_counts["row_count_before_clean"] = int(len(df))

    raw_series = df["raw_text"]
    is_null_or_blank = raw_series.isna() | raw_series.fillna("").astype(str).str.strip().eq("")
    report_counts["removed_null_or_blank"] = int(is_null_or_blank.sum())

    cleaned = df.loc[~is_null_or_blank].copy()
    cleaned["clean_text"] = cleaned["raw_text"].astype(str).map(clean_text)

    empty_clean = cleaned["clean_text"].str.strip().eq("")
    report_counts["removed_empty_after_clean"] = int(empty_clean.sum())
    cleaned = cleaned.loc[~empty_clean].copy()

    only_symbol = cleaned["clean_text"].map(is_only_emoji_or_symbol)
    report_counts["only_emoji_or_symbol_count"] = int(only_symbol.sum())

    before_dedup = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset=["clean_text"], keep="first")
    report_counts["removed_duplicates"] = int(before_dedup - len(cleaned))
    report_counts["row_count_after_clean"] = int(len(cleaned))

    return cleaned, report_counts


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_path = Path(args.output_path)
    report_path = Path(args.report_path)

    input_dir.mkdir(parents=True, exist_ok=True)

    data_files = find_data_files(input_dir)
    if not data_files and args.create_mock_if_missing:
        mock_path = create_mock_raw_data(input_dir)
        print(f"[INFO] 未发现原始数据，已生成 mock: {mock_path}")
        data_files = [mock_path]

    if not data_files:
        raise FileNotFoundError(
            f"在 {input_dir} 下未找到 csv/xlsx 原始文件。可使用 --create-mock-if-missing 先演示流程。"
        )

    unified_frames = []
    per_file_rows: Dict[str, int] = {}
    for path in data_files:
        src_df = read_source_file(path)
        per_file_rows[path.name] = int(len(src_df))
        unified_frames.append(map_and_unify(src_df, source_name=path.name))

    combined = pd.concat(unified_frames, ignore_index=True)
    processed, count_report = preprocess_dataframe(combined)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    processed.to_parquet(output_path, index=False)

    missing_fields = [
        col
        for col in STANDARD_COLUMNS
        if col != "clean_text" and col in processed.columns and processed[col].isna().all()
    ]

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "data_files": [str(p) for p in data_files],
        "per_file_rows": per_file_rows,
        "source_rows_total": int(sum(per_file_rows.values())),
        "processed_rows_total": int(len(processed)),
        "counts": count_report,
        "missing_fields_in_output": missing_fields,
        "output_path": str(output_path),
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        "[OK] preprocess done | "
        f"source={report['source_rows_total']} -> processed={report['processed_rows_total']} | "
        f"report={report_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
