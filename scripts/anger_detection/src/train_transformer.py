#!/usr/bin/env python3
"""Train Chinese transformer classifier with early stopping."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import yaml
from datasets import Dataset
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练 Transformer 文本分类模型")
    parser.add_argument("--config", default="configs/train.yaml", help="训练配置文件")
    parser.add_argument("--train-path", default="data/modeling/train.csv", help="训练集路径")
    parser.add_argument("--valid-path", default="data/modeling/valid.csv", help="验证集路径")
    parser.add_argument("--test-path", default="data/modeling/test.csv", help="测试集路径")
    parser.add_argument("--id-col", default="id", help="ID 列")
    parser.add_argument("--text-col", default="clean_text", help="文本列")
    parser.add_argument("--label-col", default="label", help="标签列")
    parser.add_argument("--output-dir", default="artifacts/transformer/best_model", help="最佳模型输出目录")
    parser.add_argument("--metrics-path", default="outputs/metrics/transformer_metrics.json", help="指标输出路径")
    parser.add_argument("--cm-path", default="outputs/metrics/transformer_confusion_matrix.png", help="混淆矩阵图路径")
    parser.add_argument(
        "--classification-report-path",
        default="outputs/metrics/transformer_classification_report.json",
        help="分类报告路径",
    )
    parser.add_argument(
        "--test-predictions-path",
        default="outputs/predictions/test_predictions.csv",
        help="测试集预测输出路径",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return pd.read_csv(path)


def clean_dataset(df: pd.DataFrame, text_col: str, label_col: str, id_col: str, name: str) -> pd.DataFrame:
    for col in [text_col, label_col]:
        if col not in df.columns:
            raise ValueError(f"{name} 缺少列: {col}")

    out = df.copy()
    if id_col not in out.columns:
        out[id_col] = [f"{name}_{i+1}" for i in range(len(out))]

    out[text_col] = out[text_col].fillna("").astype(str)
    out = out[out[text_col].str.strip() != ""].copy()

    out[label_col] = pd.to_numeric(out[label_col], errors="coerce")
    out = out[out[label_col].isin([0, 1])].copy()
    out[label_col] = out[label_col].astype(int)

    if out.empty:
        raise ValueError(f"{name} 清洗后为空")
    return out


def to_hf_dataset(df: pd.DataFrame, text_col: str, label_col: str, id_col: str) -> Dataset:
    tmp = df[[id_col, text_col, label_col]].copy()
    tmp = tmp.rename(columns={label_col: "labels"})
    return Dataset.from_pandas(tmp, preserve_index=False)


def compute_binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def plot_cm(y_true: np.ndarray, y_pred: np.ndarray, out_path: Path) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Transformer Confusion Matrix")
    ax.set_xticklabels(["0", "1"])
    ax.set_yticklabels(["0", "1"], rotation=0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def main() -> int:
    args = parse_args()
    cfg = load_yaml(Path(args.config))

    seed = int(cfg.get("seed", 42))
    model_name = str(cfg.get("model_name", "hfl/chinese-roberta-wwm-ext"))
    max_length = int(cfg.get("max_length", 256))
    epochs = int(cfg.get("epochs", 5))
    learning_rate = float(cfg.get("learning_rate", 2e-5))
    batch_size = int(cfg.get("batch_size", 8))
    eval_batch_size = int(cfg.get("eval_batch_size", 16))
    weight_decay = float(cfg.get("weight_decay", 0.01))
    early_stopping_patience = int(cfg.get("early_stopping_patience", 2))

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("WANDB_DISABLED", "true")

    set_seed(seed)

    train_df = clean_dataset(load_csv(Path(args.train_path)), args.text_col, args.label_col, args.id_col, "train")
    valid_df = clean_dataset(load_csv(Path(args.valid_path)), args.text_col, args.label_col, args.id_col, "valid")
    test_df = clean_dataset(load_csv(Path(args.test_path)), args.text_col, args.label_col, args.id_col, "test")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,
        use_safetensors=False,
    )

    train_ds = to_hf_dataset(train_df, args.text_col, args.label_col, args.id_col)
    valid_ds = to_hf_dataset(valid_df, args.text_col, args.label_col, args.id_col)
    test_ds = to_hf_dataset(test_df, args.text_col, args.label_col, args.id_col)

    def tokenize_fn(batch: dict) -> dict:
        return tokenizer(batch[args.text_col], truncation=True, max_length=max_length)

    train_ds = train_ds.map(tokenize_fn, batched=True)
    valid_ds = valid_ds.map(tokenize_fn, batched=True)
    test_ds = test_ds.map(tokenize_fn, batched=True)

    train_ds = train_ds.remove_columns([args.text_col, args.id_col])
    valid_ds = valid_ds.remove_columns([args.text_col, args.id_col])
    test_ds = test_ds.remove_columns([args.text_col, args.id_col])

    def trainer_metrics(eval_pred: tuple[np.ndarray, np.ndarray]) -> dict:
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=1)
        return compute_binary_metrics(labels, preds)

    train_output_dir = Path(args.output_dir).parent / "training_runs"
    train_output_dir.mkdir(parents=True, exist_ok=True)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    training_args = TrainingArguments(
        output_dir=str(train_output_dir),
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        num_train_epochs=epochs,
        learning_rate=learning_rate,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=eval_batch_size,
        auto_find_batch_size=True,
        weight_decay=weight_decay,
        logging_steps=50,
        save_total_limit=2,
        group_by_length=True,
        seed=seed,
        fp16=torch.cuda.is_available(),
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=trainer_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=early_stopping_patience)],
    )

    trainer.train()

    valid_pred_output = trainer.predict(valid_ds)
    test_pred_output = trainer.predict(test_ds)

    valid_logits = valid_pred_output.predictions
    valid_labels = valid_pred_output.label_ids
    valid_pred = np.argmax(valid_logits, axis=1)

    test_logits = test_pred_output.predictions
    test_labels = test_pred_output.label_ids
    test_pred = np.argmax(test_logits, axis=1)

    valid_metrics = compute_binary_metrics(valid_labels, valid_pred)
    test_metrics = compute_binary_metrics(test_labels, test_pred)

    test_probs = softmax(test_logits)
    test_max_prob = test_probs.max(axis=1)
    test_anger_prob = test_probs[:, 1]

    cm_path = Path(args.cm_path)
    plot_cm(test_labels, test_pred, cm_path)

    out_model_dir = Path(args.output_dir)
    out_model_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(out_model_dir))
    tokenizer.save_pretrained(str(out_model_dir))

    cls_report = classification_report(test_labels, test_pred, output_dict=True, zero_division=0)
    cls_report_path = Path(args.classification_report_path)
    cls_report_path.parent.mkdir(parents=True, exist_ok=True)
    with cls_report_path.open("w", encoding="utf-8") as f:
        json.dump(cls_report, f, ensure_ascii=False, indent=2)

    test_pred_df = test_df.copy().reset_index(drop=True)
    test_pred_df["true_label"] = test_labels.astype(int)
    test_pred_df["pred_label"] = test_pred.astype(int)
    test_pred_df["pred_prob"] = test_max_prob.astype(float)
    test_pred_df["anger_prob"] = test_anger_prob.astype(float)
    test_pred_df["is_correct"] = (test_pred_df["true_label"] == test_pred_df["pred_label"]).astype(int)

    test_pred_path = Path(args.test_predictions_path)
    test_pred_path.parent.mkdir(parents=True, exist_ok=True)
    test_pred_df.to_csv(test_pred_path, index=False, encoding="utf-8-sig")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_name": model_name,
        "params": {
            "max_length": max_length,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "eval_batch_size": eval_batch_size,
            "weight_decay": weight_decay,
            "early_stopping_patience": early_stopping_patience,
        },
        "data_size": {
            "train": int(len(train_df)),
            "valid": int(len(valid_df)),
            "test": int(len(test_df)),
        },
        "valid_metrics": valid_metrics,
        "test_metrics": test_metrics,
        "confusion_matrix": confusion_matrix(test_labels, test_pred, labels=[0, 1]).tolist(),
        "artifacts": {
            "best_model_dir": str(out_model_dir),
            "confusion_matrix": str(cm_path),
            "classification_report": str(cls_report_path),
            "test_predictions": str(test_pred_path),
        },
    }

    metrics_path = Path(args.metrics_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        "[OK] transformer trained | "
        f"model={model_name} | "
        f"test_f1={test_metrics['f1']:.4f}"
    )
    print(f"[OK] best_model={out_model_dir}")
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
