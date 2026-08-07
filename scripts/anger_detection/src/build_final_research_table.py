#!/usr/bin/env python3
"""Build final research tables (text-level and video-level)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成论文统计用终表")
    parser.add_argument("--master-path", default="data/processed/master.parquet", help="主数据路径")
    parser.add_argument("--predictions-path", default="outputs/predictions/full_predictions.parquet", help="全量预测路径")
    parser.add_argument("--id-col", default="id", help="主键列")
    parser.add_argument("--video-col", default="video_id", help="视频ID列")
    parser.add_argument("--time-col", default="time", help="时间列")
    parser.add_argument("--likes-col", default="likes", help="点赞列")
    parser.add_argument("--text-col", default="clean_text", help="文本列")
    parser.add_argument("--output-text-level", default="outputs/final/text_level.parquet", help="文本级终表")
    parser.add_argument("--output-video-level", default="outputs/final/video_level.parquet", help="视频级终表")
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

    master = load_table(Path(args.master_path)).copy()
    pred = load_table(Path(args.predictions_path)).copy()

    if args.id_col not in master.columns:
        raise ValueError(f"master 缺少主键列: {args.id_col}")
    if "id" not in pred.columns:
        raise ValueError("predictions 缺少 id 列")
    if "pred_label" not in pred.columns:
        raise ValueError("predictions 缺少 pred_label 列")

    required_prediction_columns = {"anger_prob", "is_low_confidence"}
    missing_prediction_columns = required_prediction_columns - set(pred.columns)
    if missing_prediction_columns:
        raise ValueError(f"predictions 缺少列: {sorted(missing_prediction_columns)}")

    master_ids = master[args.id_col].astype("string").str.strip()
    pred_ids = pred["id"].astype("string").str.strip()
    for name, ids in [("master", master_ids), ("predictions", pred_ids)]:
        if ids.isna().any() or ids.eq("").any() or ids.duplicated().any():
            raise ValueError(f"{name} 的 id 必须非空且唯一")
    master[args.id_col] = master_ids
    pred["id"] = pred_ids
    if set(master_ids) != set(pred_ids):
        raise ValueError("master 与 predictions 的 id 集合不一致")

    merged = master.merge(
        pred,
        left_on=args.id_col,
        right_on="id",
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(master):
        raise ValueError("主数据与预测结果未完整一对一合并")

    if args.video_col not in merged.columns:
        raise ValueError(f"master 缺少视频列: {args.video_col}")
    video_ids = merged[args.video_col].astype("string").str.strip()
    if video_ids.isna().any() or video_ids.eq("").any():
        raise ValueError(f"{args.video_col} 必须非空")
    merged[args.video_col] = video_ids

    pred_labels = pd.to_numeric(merged["pred_label"], errors="coerce")
    if pred_labels.isna().any() or not pred_labels.isin([0, 1]).all():
        raise ValueError("pred_label 只能为 0 或 1")
    merged["pred_label"] = pred_labels.astype(int)
    anger_prob = pd.to_numeric(merged["anger_prob"], errors="coerce")
    if not np.isfinite(anger_prob).all() or not anger_prob.between(0, 1).all():
        raise ValueError("anger_prob 必须是 [0, 1] 内的有限数值")
    merged["anger_prob"] = anger_prob
    if not pd.api.types.is_bool_dtype(merged["is_low_confidence"]):
        raise ValueError("is_low_confidence 必须为布尔值")

    if args.time_col not in merged.columns:
        merged[args.time_col] = pd.NA

    if args.likes_col not in merged.columns:
        merged[args.likes_col] = np.nan
    merged[args.likes_col] = pd.to_numeric(merged[args.likes_col], errors="coerce")

    text_col_in_merged = args.text_col
    if text_col_in_merged not in merged.columns:
        # merge 后同名列可能出现后缀，例如 clean_text_x / clean_text_y
        candidate_cols = [f"{args.text_col}_x", f"{args.text_col}_master", f"{args.text_col}_y"]
        for col in candidate_cols:
            if col in merged.columns:
                text_col_in_merged = col
                break
        else:
            raise ValueError(f"合并后缺少文本列: {args.text_col}")

    text_level = pd.DataFrame(
        {
            "id": merged[args.id_col],
            "video_id": merged[args.video_col],
            "time": merged[args.time_col],
            "clean_text": merged[text_col_in_merged].fillna("").astype(str),
            "anger_label": merged["pred_label"].astype(int),
            "anger_prob": merged["anger_prob"].astype(float),
            "is_low_confidence": merged["is_low_confidence"].astype(bool),
            "likes": merged[args.likes_col],
        }
    )

    temp = text_level.copy()
    temp["high_conf_anger"] = ((temp["anger_label"] == 1) & (~temp["is_low_confidence"])).astype(float)

    video_level = (
        temp.groupby("video_id", dropna=False)
        .agg(
            n_comments=("id", "count"),
            anger_rate=("anger_label", "mean"),
            mean_anger_prob=("anger_prob", "mean"),
            high_confidence_anger_rate=("high_conf_anger", "mean"),
            mean_likes=("likes", "mean"),
        )
        .reset_index()
    )

    out_text = Path(args.output_text_level)
    out_video = Path(args.output_video_level)
    out_text.parent.mkdir(parents=True, exist_ok=True)
    out_video.parent.mkdir(parents=True, exist_ok=True)

    text_level.to_parquet(out_text, index=False)
    video_level.to_parquet(out_video, index=False)

    print(
        "[OK] final tables built | "
        f"text_rows={len(text_level)} | video_rows={len(video_level)}"
    )
    print(f"[OK] text_level={out_text}")
    print(f"[OK] video_level={out_video}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
