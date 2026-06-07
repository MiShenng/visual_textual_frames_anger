#!/usr/bin/env python3
"""Train baseline models (TF-IDF + Logistic Regression / Linear SVM)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练基线模型（TF-IDF + LR/SVM）")
    parser.add_argument("--train-path", default="data/modeling/train.csv", help="训练集路径")
    parser.add_argument("--valid-path", default="data/modeling/valid.csv", help="验证集路径")
    parser.add_argument("--test-path", default="data/modeling/test.csv", help="测试集路径")
    parser.add_argument("--text-col", default="clean_text", help="文本列")
    parser.add_argument("--label-col", default="label", help="标签列")
    parser.add_argument("--model-type", choices=["logreg", "svm"], default="logreg", help="基线模型类型")
    parser.add_argument("--max-features", type=int, default=50000, help="TF-IDF 最大特征数")
    parser.add_argument("--ngram-min", type=int, default=1, help="n-gram 最小长度")
    parser.add_argument("--ngram-max", type=int, default=2, help="n-gram 最大长度")
    parser.add_argument("--analyzer", choices=["char", "word"], default="char", help="TF-IDF 分析粒度")
    parser.add_argument("--output-dir", default="artifacts/baseline", help="模型输出目录")
    parser.add_argument("--metrics-path", default="outputs/metrics/baseline_metrics.json", help="指标输出路径")
    parser.add_argument("--cm-path", default="outputs/metrics/baseline_confusion_matrix.png", help="混淆矩阵图片路径")
    parser.add_argument(
        "--test-predictions-path",
        default="outputs/predictions/test_predictions_baseline.csv",
        help="测试集预测明细输出路径",
    )
    return parser.parse_args()


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return pd.read_csv(path)


def validate_dataset(df: pd.DataFrame, text_col: str, label_col: str, name: str) -> pd.DataFrame:
    for col in [text_col, label_col]:
        if col not in df.columns:
            raise ValueError(f"{name} 缺少列: {col}")

    out = df.copy()
    out[text_col] = out[text_col].fillna("").astype(str)
    out = out[out[text_col].str.strip() != ""].copy()

    out[label_col] = pd.to_numeric(out[label_col], errors="coerce")
    out = out[out[label_col].isin([0, 1])].copy()
    out[label_col] = out[label_col].astype(int)

    if out.empty:
        raise ValueError(f"{name} 清洗后为空")
    return out


def build_pipeline(model_type: str, max_features: int, ngram_min: int, ngram_max: int, analyzer: str) -> Pipeline:
    vectorizer = TfidfVectorizer(
        analyzer=analyzer,
        ngram_range=(ngram_min, ngram_max),
        max_features=max_features,
        min_df=2,
        sublinear_tf=True,
    )

    if model_type == "logreg":
        classifier = LogisticRegression(max_iter=3000, class_weight="balanced")
    else:
        classifier = LinearSVC(class_weight="balanced")

    return Pipeline([("tfidf", vectorizer), ("clf", classifier)])


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -30, 30)
    return 1 / (1 + np.exp(-x))


def predict_with_probability(pipeline: Pipeline, texts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    preds = pipeline.predict(texts)
    clf = pipeline.named_steps["clf"]

    if hasattr(clf, "predict_proba"):
        probs_pos = pipeline.predict_proba(texts)[:, 1]
    elif hasattr(clf, "decision_function"):
        scores = pipeline.decision_function(texts)
        if isinstance(scores, list):
            scores = np.asarray(scores)
        probs_pos = sigmoid(np.asarray(scores))
    else:
        probs_pos = preds.astype(float)

    pred_conf = np.where(preds == 1, probs_pos, 1 - probs_pos)
    return preds.astype(int), pred_conf.astype(float)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def plot_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, out_path: Path) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Baseline Confusion Matrix")
    ax.set_xticklabels(["0", "1"])
    ax.set_yticklabels(["0", "1"], rotation=0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> int:
    args = parse_args()

    train_df = validate_dataset(load_csv(Path(args.train_path)), args.text_col, args.label_col, "train")
    valid_df = validate_dataset(load_csv(Path(args.valid_path)), args.text_col, args.label_col, "valid")
    test_df = validate_dataset(load_csv(Path(args.test_path)), args.text_col, args.label_col, "test")

    pipeline = build_pipeline(
        model_type=args.model_type,
        max_features=args.max_features,
        ngram_min=args.ngram_min,
        ngram_max=args.ngram_max,
        analyzer=args.analyzer,
    )

    pipeline.fit(train_df[args.text_col], train_df[args.label_col])

    valid_pred, valid_conf = predict_with_probability(pipeline, valid_df[args.text_col])
    test_pred, test_conf = predict_with_probability(pipeline, test_df[args.text_col])

    valid_metrics = compute_metrics(valid_df[args.label_col].to_numpy(), valid_pred)
    test_metrics = compute_metrics(test_df[args.label_col].to_numpy(), test_pred)

    cm_path = Path(args.cm_path)
    plot_confusion_matrix(test_df[args.label_col].to_numpy(), test_pred, cm_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / f"{args.model_type}_tfidf_pipeline.joblib"
    joblib.dump(pipeline, model_path)

    test_pred_df = test_df.copy()
    if "id" not in test_pred_df.columns:
        test_pred_df["id"] = [f"test_{i+1}" for i in range(len(test_pred_df))]
    test_pred_df["true_label"] = test_pred_df[args.label_col].astype(int)
    test_pred_df["pred_label"] = test_pred.astype(int)
    test_pred_df["pred_prob"] = test_conf
    test_pred_df["anger_prob"] = np.where(test_pred_df["pred_label"] == 1, test_conf, 1 - test_conf)
    test_pred_df["is_correct"] = (test_pred_df["true_label"] == test_pred_df["pred_label"]).astype(int)
    test_pred_path = Path(args.test_predictions_path)
    test_pred_path.parent.mkdir(parents=True, exist_ok=True)
    test_pred_df.to_csv(test_pred_path, index=False, encoding="utf-8-sig")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_type": args.model_type,
        "data_size": {
            "train": int(len(train_df)),
            "valid": int(len(valid_df)),
            "test": int(len(test_df)),
        },
        "params": {
            "max_features": args.max_features,
            "ngram_range": [args.ngram_min, args.ngram_max],
            "analyzer": args.analyzer,
        },
        "valid_metrics": valid_metrics,
        "test_metrics": test_metrics,
        "test_classification_report": classification_report(
            test_df[args.label_col],
            test_pred,
            output_dict=True,
            zero_division=0,
        ),
        "artifacts": {
            "model": str(model_path),
            "confusion_matrix": str(cm_path),
            "test_predictions": str(test_pred_path),
        },
    }

    metrics_path = Path(args.metrics_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        "[OK] baseline trained | "
        f"model={args.model_type} | "
        f"test_f1={test_metrics['f1']:.4f}"
    )
    print(f"[OK] model={model_path}")
    print(f"[OK] metrics={metrics_path}")
    print(f"[OK] cm={cm_path}")
    print(f"[OK] test_predictions={test_pred_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
