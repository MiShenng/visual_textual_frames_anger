# Scripts

- `frame_extraction/`: video slicing and representative-frame extraction workflow.
- `preprocessing/transcription/`: video audio extraction and transcript-generation utilities.
- `crawler/`: Douyin-first crawler used for keyword search, comment collection, and video download.
- `frame_classification/visual/`: visual frame classification workflow.
- `frame_classification/textual/`: textual frame classification workflow.
- `anger_detection/`: comment-level anger classifier pipeline.
- `analysis/`: R scripts for statistical analysis and plotting, including the original no-high-anger robustness analysis under `analysis/original_source/`.

API credentials are read from environment variables such as `QWEN_API_KEY` or `DASHSCOPE_API_KEY`; do not commit real keys.
