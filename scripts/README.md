# Scripts

论文统计分析入口：

验证环境为 R 4.4.1；绘图脚本需要 `ggplot2` 4.0.1。

```bash
Rscript scripts/analysis/run_analysis.R
Rscript scripts/analysis/plot_analysis.R
```

- `analysis/`：验证 449 条最终样本，生成统计表和复现图。
- `frame_extraction/`：视频抽帧、pHash 分段和代表帧提取。
- `preprocessing/transcription/`：音频提取和语音转写。
- `frame_classification/visual/`：视觉框架编码。
- `frame_classification/textual/`：文本框架编码。
- `anger_detection/`：评论愤怒分类。
- `crawler/`：抖音检索、评论采集和视频下载。

仓库总表保留视频 ID、链接、作者和标题；不包含登录态、API 密钥、评论原文、本地媒体或模型权重。相关采集与模型脚本需配合本地材料运行。
