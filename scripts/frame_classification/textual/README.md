# 程序 - 文本编码

该程序用于对每个视频的“文本材料包”进行双层框架编码：
- 第一层：`narrative_label`（支持 / 反对 / 中立）
- 第二层：`arousal_label`（煽动 / 说明 / 缓释）

## 输入数据

- `content/reference.csv`：主视频表（含标题等基础字段）
- `pre-analysis/数据- 叙事文本/视频语音转录汇总_480.csv`：语音转录结果
- `content/程序 - 视觉编码/output/tables/video_level_text_codes_with_ocr.csv`：OCR 抽取文本

## 运行前准备

```bash
python -m venv .venv && source .venv/bin/activate
cd scripts/frame_classification/textual
python3 -m pip install -r requirements.txt
```

配置 API Key：

```bash
# Set QWEN_API_KEY in your shell environment before running this script.
```

## 运行

仅重建文本材料包：

```bash
python3 main.py --config config.yaml --stage package
```

仅跑编码（支持断点续跑）：

```bash
python3 main.py --config config.yaml --stage code
```

仅导出表：

```bash
python3 main.py --config config.yaml --stage export
```

全流程：

```bash
python3 main.py --config config.yaml --stage all
```

## 输出

- 文本材料包 JSON：`output/text_material_packages/json/*.json`
- 文本材料包 TXT：`output/text_material_packages/txt/*.txt`
- 文本材料包汇总：`output/tables/video_level_text_material_packages.csv`
- 文本编码结果：`output/tables/video_level_text_frame_codes.csv`
