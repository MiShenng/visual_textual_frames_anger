# 视频语音转写

该目录从本地 MP4 提取 16 kHz 单声道音频，并通过 DashScope `fun-asr-realtime` 生成逐视频转写。

默认路径从仓库根目录解析：

- 输入表：`data/raw/videos_source/final_keep_videos_round2_flat.csv`
- 视频目录：`data/raw/videos_source/douyin`
- 输出目录：`outputs/transcription`

## 环境与运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/preprocessing/transcription/requirements.txt
export DASHSCOPE_API_KEY="<key>"
.venv/bin/python scripts/preprocessing/transcription/main.py
```

系统需提供 `ffmpeg`。WebSocket 地址和模型可分别通过 `DASHSCOPE_BASE_WEBSOCKET_API_URL`、`DASHSCOPE_TRANSCRIBE_MODEL` 覆盖。

参数见：

```bash
.venv/bin/python scripts/preprocessing/transcription/main.py --help
```

输出包括 `audio_files/`、逐视频 `transcripts/<video_id>/{json,txt,md}`、`merged_transcripts.md`、`failed_videos.csv` 和运行日志。

测试：

```bash
cd scripts/preprocessing/transcription
python3 -m unittest -v test_video_reader.py test_api_transcriber.py
```
