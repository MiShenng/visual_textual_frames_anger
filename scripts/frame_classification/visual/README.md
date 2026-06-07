# 程序 - 视觉编码

这个程序只做一件事：对视频切片代表帧做视觉编码，并把结果稳定落盘。

当前版本不做文本编码，不做视觉-文本合并，不做评论指标合并。

## 输入

- 切片目录：`input.slice_results_dir`
- 可选视频文本表：`input.video_text_codes_path`（用于把切片 OCR 文本并回视频级文本数据）
- 优先读取 `segments.json`，失败回退 `segments.csv`

## 输出

- `output/raw_api/visual/`：每次 API 请求原始返回
- `output/normalized/visual/`：每个切片标准化 JSON
- `output/tables/slice_level_visual_codes.csv`
- `output/tables/slice_level_visual_codes.parquet`
- `output/tables/video_level_text_codes_with_ocr.csv`
- `output/tables/video_level_text_codes_with_ocr.parquet`
- `output/tables/video_level_dual_timeline_blocks.csv`
- `output/tables/video_level_dual_timeline_blocks.parquet`
- `output/tables/video_level_dual_timeline_summary.csv`
- `output/tables/video_level_dual_timeline_summary.parquet`
- `output/logs/`：运行日志

## 断点续跑

- 默认 `pipeline.overwrite_existing: false`
- 已存在且 `status=success/skipped` 的切片不会重复请求

## 配置

### 1) API Key

```bash
cp .env.example .env
```

把 `.env` 里的 `QWEN_API_KEY` 填好，或直接在系统环境变量里设置。

### 2) 提示词与类目

你后续可直接替换：

- `coding.visual_system_prompt_path` 指向的提示词文件
- `coding.visual_labels`
- `coding.arousal_labels`
- `coding.confidence_labels`
- `coding.visual_label_aliases`
- `coding.arousal_label_aliases`
- `coding.confidence_aliases`

速度相关参数（`api`）：

- `enable_thinking`：是否开启思考。视觉批处理建议设为 `false` 提速。
- `max_completion_tokens`：限制单次返回上限，防止长响应拖慢或超时。
- `visual_concurrency`：并发线程数，越高吞吐越高，但受 API 限流影响。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

全流程（发现 -> 编码 -> 导出）：

```bash
python main.py --config config.yaml --stage all
```

仅视觉编码并导出：

```bash
python main.py --config config.yaml --stage visual
```

运行时终端会显示实时进度条：百分比、已完成/剩余切片数、ETA 和预计完成时刻（适合 VS Code 集成终端观察）。

仅重建导出表（不请求 API）：

```bash
python main.py --config config.yaml --stage export
```

## 目录结构

```text
程序 - 视觉编码/
├── main.py
├── config.yaml
├── .env.example
├── requirements.txt
├── README.md
├── prompts/
│   └── visual_system_prompt.txt
└── src/
    ├── __init__.py
    ├── config.py
    ├── discovery.py
    ├── io_utils.py
    ├── prompts.py
    ├── qwen_client.py
    └── pipeline.py
```
