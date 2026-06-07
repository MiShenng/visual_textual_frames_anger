#!/usr/bin/env python3
"""Run batch inference on full dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对全量文本做批量推理")
    parser.add_argument("--input-path", default="data/processed/master.parquet", help="全量数据路径")
    parser.add_argument("--model-type", choices=["transformer", "baseline"], default="transformer", help="模型类型")
    parser.add_argument(
        "--model-path",
        default="artifacts/transformer/best_model",
        help="模型路径（transformer 目录 或 baseline joblib 文件）",
    )
    parser.add_argument("--id-col", default="id", help="ID 列")
    parser.add_argument("--text-col", default="clean_text", help="文本列")
    parser.add_argument("--batch-size", type=int, default=32, help="批量大小")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.60, help="低置信阈值")
    parser.add_argument(
        "--output-parquet",
        default="outputs/predictions/full_predictions.parquet",
        help="Parquet 输出路径",
    )
    parser.add_argument("--output-csv", default="outputs/predictions/full_predictions.csv", help="CSV 输出路径")
    return parser.parse_args()


def load_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件格式: {path}")


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def predict_transformer(df: pd.DataFrame, model_dir: Path, text_col: str, batch_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)

    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    model.to(device)
    model.eval()

    texts = df[text_col].fillna("").astype(str).tolist()
    all_pred = []
    all_conf = []
    all_anger_prob = []

    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            encoded = tokenizer(
                batch,
                truncation=True,
                padding=True,
                return_tensors="pt",
                max_length=256,
            )
            encoded = {k: v.to(device) for k, v in encoded.items()}
            logits = model(**encoded).logits.detach().cpu().numpy()
            probs = softmax(logits)

            pred = probs.argmax(axis=1)
            conf = probs.max(axis=1)
            anger_prob = probs[:, 1] if probs.shape[1] > 1 else conf

            all_pred.append(pred)
            all_conf.append(conf)
            all_anger_prob.append(anger_prob)

    return (
        np.concatenate(all_pred).astype(int),
        np.concatenate(all_conf).astype(float),
        np.concatenate(all_anger_prob).astype(float),
    )


def predict_baseline(df: pd.DataFrame, model_path: Path, text_col: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pipeline = joblib.load(model_path)
    texts = df[text_col].fillna("").astype(str)
    pred = pipeline.predict(texts).astype(int)

    clf = pipeline.named_steps.get("clf")
    if hasattr(clf, "predict_proba"):
        probs_pos = pipeline.predict_proba(texts)[:, 1]
    elif hasattr(clf, "decision_function"):
        scores = pipeline.decision_function(texts)
        scores = np.clip(scores, -30, 30)
        probs_pos = 1 / (1 + np.exp(-scores))
    else:
        probs_pos = pred.astype(float)

    conf = np.where(pred == 1, probs_pos, 1 - probs_pos)
    anger_prob = probs_pos.astype(float)
    return pred, conf.astype(float), anger_prob


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    model_path = Path(args.model_path)

    df = load_table(input_path)
    if args.text_col not in df.columns:
        raise ValueError(f"输入数据缺少文本列: {args.text_col}")

    if args.id_col not in df.columns:
        df[args.id_col] = [f"auto_{i+1}" for i in range(len(df))]

    if args.model_type == "transformer":
        pred, conf, anger_prob = predict_transformer(df, model_path, args.text_col, args.batch_size)
    else:
        pred, conf, anger_prob = predict_baseline(df, model_path, args.text_col)

    out_df = pd.DataFrame(
        {
            "id": df[args.id_col],
            "clean_text": df[args.text_col].fillna("").astype(str),
            "pred_label": pred.astype(int),
            "pred_prob": conf.astype(float),
            "anger_prob": anger_prob.astype(float),
            "is_low_confidence": conf.astype(float) < args.low_confidence_threshold,
        }
    )

    out_parquet = Path(args.output_parquet)
    out_csv = Path(args.output_csv)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    out_df.to_parquet(out_parquet, index=False)
    out_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    print(
        "[OK] full prediction done | "
        f"rows={len(out_df)} | low_conf={int(out_df['is_low_confidence'].sum())}"
    )
    print(f"[OK] parquet={out_parquet}")
    print(f"[OK] csv={out_csv}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
