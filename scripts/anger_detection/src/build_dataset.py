#!/usr/bin/env python3
"""Build train/valid/test splits from adjudicated labels."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

POSITIVE_VALUES = {
    "1",
    "anger",
    "angry",
    "愤怒",
    "是",
    "yes",
    "y",
    "true",
    "t",
    "pos",
    "positive",
}

NEGATIVE_VALUES = {
    "0",
    "non-anger",
    "non_anger",
    "nonanger",
    "非愤怒",
    "否",
    "no",
    "n",
    "false",
    "f",
    "neg",
    "negative",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据仲裁标签构建 train/valid/test 数据集")
    parser.add_argument("--input-path", default="data/annotation/annotation_sample.csv", help="标注数据路径（csv/xlsx）")
    parser.add_argument("--id-col", default="id", help="样本ID列")
    parser.add_argument("--text-col", default="clean_text", help="文本列")
    parser.add_argument("--label-col", default="adjudicated_label", help="仲裁标签列")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="训练集比例")
    parser.add_argument("--valid-ratio", type=float, default=0.1, help="验证集比例")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="测试集比例")
    parser.add_argument("--random-state", type=int, default=42, help="随机种子")
    parser.add_argument("--output-dir", default="data/modeling", help="输出目录")
    parser.add_argument(
        "--report-path",
        default="outputs/metrics/dataset_split_report.json",
        help="切分报告输出路径",
    )
    return parser.parse_args()


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件格式: {path}")


def normalize_binary_label(value: object) -> Optional[int]:
    if pd.isna(value):
        return None

    if isinstance(value, (int, np.integer)):
        return int(value) if int(value) in (0, 1) else None

    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return None
        as_int = int(value)
        return as_int if as_int in (0, 1) and float(value) == float(as_int) else None

    token = str(value).strip().lower()
    if token in POSITIVE_VALUES:
        return 1
    if token in NEGATIVE_VALUES:
        return 0
    return None


def validate_ratios(train_ratio: float, valid_ratio: float, test_ratio: float) -> None:
    ratio_sum = train_ratio + valid_ratio + test_ratio
    if abs(ratio_sum - 1.0) > 1e-8:
        raise ValueError(f"train/valid/test 比例之和必须为 1，当前为 {ratio_sum:.6f}")
    if min(train_ratio, valid_ratio, test_ratio) <= 0:
        raise ValueError("train/valid/test 比例都必须 > 0")


def ensure_stratifiable(df: pd.DataFrame, label_col: str) -> None:
    label_counts = df[label_col].value_counts()
    if len(label_counts) < 2:
        raise ValueError("仅检测到一个类别，无法进行二分类分层切分")

    min_count = int(label_counts.min())
    if min_count < 3:
        raise ValueError(
            "最小类别样本数过少（<3），无法保证 train/valid/test 分层切分。"
            f"当前类别计数: {label_counts.to_dict()}"
        )


def split_dataset(
    df: pd.DataFrame,
    label_col: str,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    temp_ratio = valid_ratio + test_ratio

    train_df, temp_df = train_test_split(
        df,
        test_size=temp_ratio,
        random_state=random_state,
        stratify=df[label_col],
    )

    valid_share_in_temp = valid_ratio / temp_ratio
    valid_df, test_df = train_test_split(
        temp_df,
        test_size=1 - valid_share_in_temp,
        random_state=random_state,
        stratify=temp_df[label_col],
    )

    return train_df.reset_index(drop=True), valid_df.reset_index(drop=True), test_df.reset_index(drop=True)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir)
    report_path = Path(args.report_path)

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    validate_ratios(args.train_ratio, args.valid_ratio, args.test_ratio)

    df = load_table(input_path)
    required = [args.text_col, args.label_col]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"输入文件缺少必要列: {col}")

    work = df.copy()
    if args.id_col not in work.columns:
        work[args.id_col] = [f"auto_{i+1}" for i in range(len(work))]

    work[args.text_col] = work[args.text_col].fillna("").astype(str).str.strip()
    work["label"] = work[args.label_col].map(normalize_binary_label)

    clean = work[(work[args.text_col] != "") & work["label"].notna()].copy()
    clean["label"] = clean["label"].astype(int)

    if clean.empty:
        raise ValueError("无可用样本：请检查 clean_text 与 adjudicated_label")

    ensure_stratifiable(clean, "label")

    train_df, valid_df, test_df = split_dataset(
        clean,
        label_col="label",
        train_ratio=args.train_ratio,
        valid_ratio=args.valid_ratio,
        test_ratio=args.test_ratio,
        random_state=args.random_state,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.csv"
    valid_path = output_dir / "valid.csv"
    test_path = output_dir / "test.csv"

    train_df.to_csv(train_path, index=False, encoding="utf-8-sig")
    valid_df.to_csv(valid_path, index=False, encoding="utf-8-sig")
    test_df.to_csv(test_path, index=False, encoding="utf-8-sig")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_path": str(input_path),
        "total_rows": int(len(df)),
        "usable_rows": int(len(clean)),
        "label_distribution": clean["label"].value_counts().sort_index().to_dict(),
        "split_sizes": {
            "train": int(len(train_df)),
            "valid": int(len(valid_df)),
            "test": int(len(test_df)),
        },
        "split_label_distribution": {
            "train": train_df["label"].value_counts().sort_index().to_dict(),
            "valid": valid_df["label"].value_counts().sort_index().to_dict(),
            "test": test_df["label"].value_counts().sort_index().to_dict(),
        },
        "output_files": {
            "train": str(train_path),
            "valid": str(valid_path),
            "test": str(test_path),
        },
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        "[OK] dataset built | "
        f"usable={len(clean)} | train/valid/test={len(train_df)}/{len(valid_df)}/{len(test_df)}"
    )
    print(f"[OK] report={report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
