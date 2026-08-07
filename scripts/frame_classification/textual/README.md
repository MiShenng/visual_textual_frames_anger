# 文本框架编码

该程序把视频标题、语音转写、字幕和 OCR 文本合并为材料包，并编码 `narrative_label`（支持/反对/中立）与 `arousal_label`（`Intensifying` / `Informational` / `Mitigating`）。

输入、模型、标签和输出路径统一定义在 `config.yaml`。其中视频主表、转写和 OCR 表属于本地受限材料，公开仓库不提供。

## 环境与运行

```bash
cd scripts/frame_classification/textual
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export QWEN_API_KEY="<key>"
.venv/bin/python main.py --config config.yaml --stage all
```

`--stage` 可取：

- `package`：生成文本材料包。
- `code`：调用模型编码，保留已成功结果。
- `export`：仅重建汇总表。
- `all`：执行上述阶段。

输出写入仓库根目录的 `outputs/frame_classification/textual/`，包括材料包、标准化响应、API 原始响应、日志和视频级编码表。
