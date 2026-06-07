# 评论区情绪分类研究流水线（可复现）

本项目用于中文社交媒体评论文本的“愤怒表达（anger=1）”识别，并预留后续扩展到“道德愤怒”等多分类任务。

## 1. 研究任务覆盖

已实现端到端脚本：
1. 数据预处理（统一字段、清洗、去重）
2. 分层抽样用于人工标注
3. 标注一致性评估（Cohen's Kappa）
4. 训练集构建（train/valid/test 分层切分）
5. 基线模型训练（TF-IDF + LR / Linear SVM）
6. 主模型训练（Transformer）
7. 全量推理
8. 误差分析与主动学习样本导出
9. 论文统计终表构建（文本级、视频级）

## 2. 目录结构

```text
.
├── README.md
├── labelbook.md
├── requirements.txt
├── configs/
│   └── train.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   ├── annotation/
│   └── modeling/
├── src/
│   ├── preprocess.py
│   ├── sample_for_annotation.py
│   ├── compute_agreement.py
│   ├── build_dataset.py
│   ├── train_baseline.py
│   ├── train_transformer.py
│   ├── predict_full.py
│   ├── error_analysis.py
│   └── build_final_research_table.py
├── artifacts/
│   ├── baseline/
│   └── transformer/
└── outputs/
    ├── logs/
    ├── metrics/
    ├── predictions/
    ├── review/
    └── final/
```

## 3. 环境安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

## 4. 输入数据要求

将原始 `csv/xlsx` 放入 `data/raw/`。

预处理后会统一输出 `data/processed/master.parquet`，标准字段：
- `id`
- `raw_text`
- `clean_text`
- `time`
- `post_id`
- `video_id`
- `user_id`
- `parent_id`
- `likes`

如源文件缺失某些字段，脚本会保留已有字段并将缺失字段置空。

## 5. 完整运行流程（推荐顺序）

### Step 1. 预处理
```bash
python src/preprocess.py \
  --input-dir data/raw \
  --output-path data/processed/master.parquet \
  --report-path outputs/logs/preprocess_report.json
```

### Step 2. 标注抽样（默认 5000）
```bash
python src/sample_for_annotation.py \
  --input-path data/processed/master.parquet \
  --sample-size 5000 \
  --output-csv data/annotation/annotation_sample.csv \
  --output-xlsx data/annotation/annotation_sample.xlsx
```

### Step 3. 人工标注
按 `labelbook.md` 规则填写：
- `label_annotator_a`
- `label_annotator_b`
- `adjudicated_label`（仲裁后）
- `notes`

### Step 4. 一致性评估
```bash
python src/compute_agreement.py \
  --input-path data/annotation/annotation_sample.csv \
  --output-report outputs/metrics/agreement_report.json \
  --output-disagreement outputs/review/disagreement_cases.csv
```

### Step 5. 构建建模数据集
```bash
python src/build_dataset.py \
  --input-path data/annotation/annotation_sample.csv \
  --label-col adjudicated_label \
  --train-ratio 0.8 \
  --valid-ratio 0.1 \
  --test-ratio 0.1 \
  --output-dir data/modeling
```

输出：
- `data/modeling/train.csv`
- `data/modeling/valid.csv`
- `data/modeling/test.csv`

### Step 6A. 训练基线模型
```bash
python src/train_baseline.py \
  --train-path data/modeling/train.csv \
  --valid-path data/modeling/valid.csv \
  --test-path data/modeling/test.csv \
  --model-type logreg
```

可选 `--model-type svm`。

### Step 6B. 训练 Transformer 主模型
```bash
python src/train_transformer.py \
  --config configs/train.yaml \
  --train-path data/modeling/train.csv \
  --valid-path data/modeling/valid.csv \
  --test-path data/modeling/test.csv
```

默认配置（见 `configs/train.yaml`）：
- model: `hfl/chinese-roberta-wwm-ext`
- epochs: `5`
- learning_rate: `2e-5`
- batch_size: `8`
- early_stopping_patience: `2`

### Step 7. 全量推理（300,000 条）
使用 Transformer 最佳模型：
```bash
python src/predict_full.py \
  --input-path data/processed/master.parquet \
  --model-type transformer \
  --model-path artifacts/transformer/best_model \
  --low-confidence-threshold 0.60 \
  --output-parquet outputs/predictions/full_predictions.parquet \
  --output-csv outputs/predictions/full_predictions.csv
```

如需用基线模型快速试跑：
```bash
python src/predict_full.py \
  --input-path data/processed/master.parquet \
  --model-type baseline \
  --model-path artifacts/baseline/logreg_tfidf_pipeline.joblib
```

### Step 8. 误差分析与复核样本导出
```bash
python src/error_analysis.py \
  --test-predictions-path outputs/predictions/test_predictions.csv \
  --full-predictions-path outputs/predictions/full_predictions.parquet
```

输出：
- `outputs/review/test_errors.csv`
- `outputs/review/low_confidence_cases.csv`
- `outputs/review/high_confidence_examples.csv`

### Step 9. 构建论文终表
```bash
python src/build_final_research_table.py \
  --master-path data/processed/master.parquet \
  --predictions-path outputs/predictions/full_predictions.parquet \
  --output-text-level outputs/final/text_level.parquet \
  --output-video-level outputs/final/video_level.parquet
```

输出：
- 文本级：`outputs/final/text_level.parquet`
- 视频级：`outputs/final/video_level.parquet`

## 6. 常见问题

- `No raw data file found`：`data/raw/` 没有 `csv/xlsx`。
- `缺少 clean_text`：先运行 `preprocess.py`。
- `No valid labels` / `无法计算 Kappa`：标注列值未规范化（建议统一 `0/1`）。
- `分层切分失败`：某类别样本太少，先补充标注样本。
- Transformer OOM：已启用 `auto_find_batch_size=True` 自动降批次，必要时在配置里手动降低 `batch_size`。

## 7. 无真实数据时的演示

```bash
python src/preprocess.py --create-mock-if-missing
python src/sample_for_annotation.py --create-mock-if-missing
```

## 8. 多分类扩展（道德愤怒）

扩展建议：
1. 在 `labelbook.md` 扩展标签体系（`moral_anger`, `other_negative`, `neutral_or_other`）。
2. 将 `adjudicated_label` 从二分类扩展为多分类值。
3. 调整建模脚本至 `num_labels=4` 并输出 macro/micro 指标。
4. 保留 `anger` 二分类映射字段，保证与第一阶段结果可比。

