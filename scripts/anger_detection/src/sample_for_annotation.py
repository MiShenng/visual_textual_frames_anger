#!/usr/bin/env python3
"""Sample records for dual-annotator labeling with stratification fallback."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
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
    parser.add_argument("--sample-size", type=int, default=10000, help="抽样条数")
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
    return parser.parse_args()


def load_master(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的输入格式: {path}")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    output_csv = Path(args.output_csv)
    output_xlsx = Path(args.output_xlsx)

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
    sampled = valid_df.sample(n=sample_size, random_state=args.random_state).reset_index(drop=True)

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
        f"input={len(valid_df)} sampled={len(out_df)} | random_state={args.random_state}"
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
