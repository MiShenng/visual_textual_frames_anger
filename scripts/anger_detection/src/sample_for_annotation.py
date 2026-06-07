#!/usr/bin/env python3
"""Sample records for dual-annotator labeling with stratification fallback."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ANNOTATION_COLUMNS = [
    "id",
    "clean_text",
    "label_annotator_a",
    "label_annotator_b",
    "adjudicated_label",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为人工标注抽样数据")
    parser.add_argument("--input-path", default="data/processed/master.parquet", help="主数据路径")
    parser.add_argument("--sample-size", type=int, default=5000, help="抽样条数")
    parser.add_argument(
        "--output-csv",
        default="data/annotation/annotation_sample.csv",
        help="标注样本 CSV 输出路径",
    )
    parser.add_argument(
        "--output-xlsx",
        default="data/annotation/annotation_sample.xlsx",
        help="标注样本 XLSX 输出路径",
    )
    parser.add_argument("--random-state", type=int, default=42, help="随机种子")
    parser.add_argument(
        "--create-mock-if-missing",
        action="store_true",
        help="若主数据缺失，自动生成 mock 主数据后继续",
    )
    return parser.parse_args()


def create_mock_master(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mock_df = pd.DataFrame(
        {
            "id": [f"m{i:05d}" for i in range(1, 101)],
            "raw_text": [f"示例文本{i}" for i in range(1, 101)],
            "clean_text": [f"示例文本{i}" for i in range(1, 101)],
            "time": pd.date_range("2026-01-01", periods=100, freq="D").astype(str),
            "post_id": [f"p{i%10}" for i in range(1, 101)],
            "video_id": [f"v{i%8}" for i in range(1, 101)],
            "user_id": [f"u{i%20}" for i in range(1, 101)],
            "parent_id": [pd.NA for _ in range(100)],
            "likes": np.random.randint(0, 100, size=100),
        }
    )
    mock_df.to_parquet(path, index=False)


def load_master(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的输入格式: {path}")


def allocate_by_largest_remainder(group_sizes: pd.Series, n: int) -> pd.Series:
    proportions = group_sizes / group_sizes.sum()
    raw_alloc = proportions * n
    alloc = np.floor(raw_alloc).astype(int)

    remainder = n - int(alloc.sum())
    if remainder > 0:
        frac = (raw_alloc - alloc).sort_values(ascending=False)
        for idx in frac.index[:remainder]:
            alloc.loc[idx] += 1
    elif remainder < 0:
        frac = (raw_alloc - alloc).sort_values(ascending=True)
        for idx in frac.index[: abs(remainder)]:
            if alloc.loc[idx] > 0:
                alloc.loc[idx] -= 1

    return alloc


def build_strata_columns(df: pd.DataFrame) -> List[str]:
    strata_cols: List[str] = []

    if "video_id" in df.columns:
        video = df["video_id"].fillna("MISSING").astype(str).str.strip().replace("", "MISSING")
        if video.nunique() > 1:
            top_k = min(50, video.nunique())
            top_ids = set(video.value_counts().head(top_k).index.tolist())
            df["_video_group"] = np.where(video.isin(top_ids), video, "OTHER")
            strata_cols.append("_video_group")

    if "time" in df.columns:
        parsed_time = pd.to_datetime(df["time"], errors="coerce")
        if parsed_time.notna().sum() > 0:
            df["_time_group"] = parsed_time.dt.to_period("M").astype(str).replace("NaT", "MISSING")
            strata_cols.append("_time_group")

    text_len = df["clean_text"].fillna("").astype(str).str.len()
    if text_len.nunique() > 1:
        q = min(5, text_len.nunique())
        df["_len_group"] = pd.qcut(text_len, q=q, duplicates="drop").astype(str)
        strata_cols.append("_len_group")

    return strata_cols


def stratified_sample(df: pd.DataFrame, sample_size: int, random_state: int) -> tuple[pd.DataFrame, List[str]]:
    if sample_size >= len(df):
        return df.copy(), []

    strata_cols = build_strata_columns(df)
    if not strata_cols:
        sampled = df.sample(n=sample_size, random_state=random_state)
        return sampled, []

    df["_stratum_key"] = df[strata_cols].astype(str).agg("|".join, axis=1)
    group_sizes = df["_stratum_key"].value_counts()

    alloc = allocate_by_largest_remainder(group_sizes=group_sizes, n=sample_size)

    sampled_parts = []
    for key, n_take in alloc.items():
        if n_take <= 0:
            continue
        group_df = df[df["_stratum_key"] == key]
        n_take = min(n_take, len(group_df))
        sampled_parts.append(group_df.sample(n=n_take, random_state=random_state))

    if sampled_parts:
        sampled = pd.concat(sampled_parts, axis=0)
    else:
        sampled = pd.DataFrame(columns=df.columns)

    # If due to rounding/empty groups not enough, backfill randomly.
    if len(sampled) < sample_size:
        remaining = df.drop(index=sampled.index, errors="ignore")
        need = sample_size - len(sampled)
        if len(remaining) > 0:
            sampled = pd.concat(
                [sampled, remaining.sample(n=min(need, len(remaining)), random_state=random_state)],
                axis=0,
            )

    sampled = sampled.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return sampled.head(sample_size), strata_cols


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    output_csv = Path(args.output_csv)
    output_xlsx = Path(args.output_xlsx)

    if not input_path.exists() and args.create_mock_if_missing:
        create_mock_master(input_path)
        print(f"[INFO] 主数据缺失，已生成 mock: {input_path}")

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    df = load_master(input_path)
    if "clean_text" not in df.columns:
        raise ValueError("输入数据缺少 clean_text 列，请先运行 preprocess.py")

    if "id" not in df.columns:
        df["id"] = [f"auto_{i+1}" for i in range(len(df))]

    valid_df = df[df["clean_text"].fillna("").astype(str).str.strip() != ""].copy()
    if valid_df.empty:
        raise ValueError("clean_text 全为空，无法抽样")

    sample_size = min(args.sample_size, len(valid_df))
    sampled, strata_cols = stratified_sample(valid_df, sample_size=sample_size, random_state=args.random_state)

    out_df = sampled[["id", "clean_text"]].copy()
    out_df["label_annotator_a"] = pd.NA
    out_df["label_annotator_b"] = pd.NA
    out_df["adjudicated_label"] = pd.NA
    out_df["notes"] = pd.NA
    out_df = out_df[ANNOTATION_COLUMNS]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)

    out_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    out_df.to_excel(output_xlsx, index=False)

    print(
        "[OK] annotation sample exported | "
        f"input={len(valid_df)} sampled={len(out_df)} | "
        f"strata={strata_cols if strata_cols else 'random'}"
    )
    print(f"[OK] csv={output_csv}")
    print(f"[OK] xlsx={output_xlsx}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
