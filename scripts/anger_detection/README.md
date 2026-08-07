# 评论愤怒分类

该目录保存评论级 `anger` 二分类代码。

## 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

命令从 `scripts/anger_detection/` 执行。原始 CSV/XLSX 放在 `data/raw/`；预处理后的标准字段为 `id`、`raw_text`、`clean_text`、`time`、`post_id`、`video_id`、`user_id`、`parent_id`、`comment_level` 和 `likes`。存在 `comment_level` 时仅保留一级评论，重复记录按评论 ID 去除。

## 入口

| 文件 | 功能 |
|---|---|
| `src/preprocess.py` | 清洗、统一字段并生成 `data/processed/master.parquet` |
| `src/sample_for_annotation.py` | 随机导出 10,000 条人工标注样本 |
| `src/compute_agreement.py` | 计算 Cohen's Kappa 并导出分歧案例 |
| `src/build_dataset.py` | 按标签分层生成 train/valid/test |
| `src/train_baseline.py` | 训练 TF-IDF + Logistic Regression/Linear SVM |
| `src/train_transformer.py` | 按 `configs/train.yaml` 训练 Transformer |
| `src/predict_full.py` | 对完整评论表推理 |
| `src/error_analysis.py` | 导出测试错误和低置信度案例 |
| `src/build_final_research_table.py` | 生成文本级和视频级汇总表 |

各入口的参数以 `python src/<文件名> --help` 为准。人工标注表使用 `label_annotator_a`、`label_annotator_b`、`adjudicated_label` 和 `notes`；建模标签为 `0/1`。

模型、指标、预测和复核输出分别写入 `artifacts/` 与 `outputs/`。评论原文、用户标识和模型权重不进入公开仓库。
