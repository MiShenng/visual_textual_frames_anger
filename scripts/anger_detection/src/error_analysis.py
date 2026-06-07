#!/usr/bin/env python3
"""Export error-analysis review files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="误差分析与主动学习样本导出")
    parser.add_argument(
        "--test-predictions-path",
        default="outputs/predictions/test_predictions.csv",
        help="测试集预测明细路径（需包含 true_label/pred_label）",
    )
    parser.add_argument(
        "--full-predictions-path",
        default="outputs/predictions/full_predictions.parquet",
        help="全量预测路径（parquet/csv）",
    )
    parser.add_argument("--max-test-errors", type=int, default=500, help="导出误判样本上限")
    parser.add_argument("--max-low-confidence", type=int, default=1000, help="导出低置信样本上限")
    parser.add_argument(
        "--max-high-confidence-per-class",
        type=int,
        default=200,
        help="每个类别导出高置信代表样本上限",
    )
    parser.add_argument("--output-test-errors", default="outputs/review/test_errors.csv", help="测试误判输出路径")
    parser.add_argument(
        "--output-low-confidence",
        default="outputs/review/low_confidence_cases.csv",
        help="低置信样本输出路径",
    )
    parser.add_argument(
        "--output-high-confidence",
        default="outputs/review/high_confidence_examples.csv",
        help="高置信样本输出路径",
    )
    return parser.parse_args()


def load_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件格式: {path}")


def main() -> int:
    args = parse_args()

    test_df = load_table(Path(args.test_predictions_path))
    full_df = load_table(Path(args.full_predictions_path))

    for col in ["pred_label", "pred_prob"]:
        if col not in full_df.columns:
            raise ValueError(f"full_predictions 缺少列: {col}")

    if "is_low_confidence" not in full_df.columns:
        full_df["is_low_confidence"] = full_df["pred_prob"] < 0.60

    if "true_label" not in test_df.columns or "pred_label" not in test_df.columns:
        raise ValueError("test_predictions 需包含 true_label 与 pred_label")

    # 1) 测试集误判样本
    test_errors = test_df[test_df["true_label"] != test_df["pred_label"]].copy()
    if "pred_prob" in test_errors.columns:
        test_errors = test_errors.sort_values(by="pred_prob", ascending=True)
    test_errors = test_errors.head(args.max_test_errors)

    # 2) 全量低置信样本
    low_conf = full_df[full_df["is_low_confidence"].astype(bool)].copy()
    low_conf = low_conf.sort_values(by="pred_prob", ascending=True).head(args.max_low_confidence)

    # 3) 各类别高置信代表样本
    high_conf_parts = []
    for label, sub in full_df.groupby("pred_label"):
        top = sub.sort_values(by="pred_prob", ascending=False).head(args.max_high_confidence_per_class)
        high_conf_parts.append(top)
    high_conf = pd.concat(high_conf_parts, ignore_index=True) if high_conf_parts else pd.DataFrame(columns=full_df.columns)

    out_test = Path(args.output_test_errors)
    out_low = Path(args.output_low_confidence)
    out_high = Path(args.output_high_confidence)
    out_test.parent.mkdir(parents=True, exist_ok=True)
    out_low.parent.mkdir(parents=True, exist_ok=True)
    out_high.parent.mkdir(parents=True, exist_ok=True)

    test_errors.to_csv(out_test, index=False, encoding="utf-8-sig")
    low_conf.to_csv(out_low, index=False, encoding="utf-8-sig")
    high_conf.to_csv(out_high, index=False, encoding="utf-8-sig")

    print(
        "[OK] error analysis done | "
        f"test_errors={len(test_errors)} | low_conf={len(low_conf)} | high_conf={len(high_conf)}"
    )
    print(f"[OK] test_errors={out_test}")
    print(f"[OK] low_confidence={out_low}")
    print(f"[OK] high_confidence={out_high}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
