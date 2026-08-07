# 视觉框架编码

该程序读取视频代表帧，编码视觉立场（支持/反对/中立）与唤醒方式（`Intensifying` / `Informational` / `Mitigating`），并生成切片级和视频级时间轴表。

输入目录、模型、标签、批量参数和输出路径统一定义在 `config.yaml`。代表帧和视频文本表属于本地受限材料，公开仓库不提供。

## 环境与运行

```bash
cd scripts/frame_classification/visual
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export QWEN_API_KEY="<key>"
.venv/bin/python main.py --config config.yaml --stage all
```

`--stage visual` 执行视觉编码并导出，`--stage export` 仅由已有标准化结果重建表。`pipeline.overwrite_existing: false` 时保留状态为 `success` 或 `skipped` 的结果。

输出写入仓库根目录的 `outputs/frame_classification/visual/`，包括 API 原始响应、标准化 JSON、运行日志、切片级视觉表、视频级双层时间轴表及 OCR 汇总表。
