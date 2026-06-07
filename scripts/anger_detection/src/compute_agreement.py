#!/usr/bin/env python3
"""Compute inter-annotator agreement (Cohen's Kappa) and export disagreements."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

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
    parser = argparse.ArgumentParser(description="计算双标注一致性（Cohen's Kappa）")
    parser.add_argument(
        "--input-path",
        default="data/annotation/annotation_sample.csv",
        help="标注文件路径（csv/xlsx）",
    )
    parser.add_argument(
        "--annotator-a-col",
        default="label_annotator_a",
        help="标注员A标签列名",
    )
    parser.add_argument(
        "--annotator-b-col",
        default="label_annotator_b",
        help="标注员B标签列名",
    )
    parser.add_argument(
        "--output-report",
        default="outputs/metrics/agreement_report.json",
        help="一致性报告输出路径",
    )
    parser.add_argument(
        "--output-disagreement",
        default="outputs/review/disagreement_cases.csv",
        help="分歧样本输出路径",
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


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    output_report = Path(args.output_report)
    output_disagreement = Path(args.output_disagreement)

    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    df = load_table(input_path)
    if args.annotator_a_col not in df.columns or args.annotator_b_col not in df.columns:
        raise ValueError(
            f"缺少标注列: {args.annotator_a_col} / {args.annotator_b_col}. "
            "请检查输入文件列名。"
        )

    work = df.copy()
    work["_a"] = work[args.annotator_a_col].map(normalize_binary_label)
    work["_b"] = work[args.annotator_b_col].map(normalize_binary_label)

    valid = work[work["_a"].notna() & work["_b"].notna()].copy()
    if valid.empty:
        raise ValueError("无可用标注（A/B 都需为可识别标签），无法计算 Kappa")

    y_a = valid["_a"].astype(int)
    y_b = valid["_b"].astype(int)

    kappa = float(cohen_kappa_score(y_a, y_b))
    cm = confusion_matrix(y_a, y_b, labels=[0, 1])

    disagreement = valid[y_a != y_b].copy()
    keep_cols = [c for c in ["id", "clean_text", args.annotator_a_col, args.annotator_b_col] if c in disagreement.columns]
    disagreement = disagreement[keep_cols]

    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_disagreement.parent.mkdir(parents=True, exist_ok=True)

    disagreement.to_csv(output_disagreement, index=False, encoding="utf-8-sig")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_path": str(input_path),
        "total_rows": int(len(df)),
        "valid_rows": int(len(valid)),
        "invalid_or_missing_rows": int(len(df) - len(valid)),
        "cohen_kappa": kappa,
        "confusion_matrix": {
            "labels": [0, 1],
            "matrix": cm.tolist(),
            "note": "rows=annotator_a, cols=annotator_b",
        },
        "disagreement_count": int(len(disagreement)),
        "disagreement_path": str(output_disagreement),
    }

    with output_report.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        "[OK] agreement computed | "
        f"valid={report['valid_rows']}/{report['total_rows']} | "
        f"kappa={kappa:.4f}"
    )
    print("[OK] confusion_matrix rows(A) x cols(B):")
    print(cm)
    print(f"[OK] disagreement={output_disagreement}")
    print(f"[OK] report={output_report}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
