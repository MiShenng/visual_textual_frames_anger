# 提取视频文本

这套程序参考你给的播客转录主流程，但输入改成了**你自己的本地 mp4 视频**，转写后端改成 **阿里云百炼 DashScope 北京区 `fun-asr-realtime`**。

主链路是：

1. 从视频参考表读取本地视频 ID。
2. 从 `mp4` 中提取单声道 `16k` 音频。
3. 调用 DashScope 北京区 `fun-asr-realtime` 直接识别本地音频文件。
5. 为每条视频保存 `json / txt / md` 三种结果。
6. 合并所有单条转写结果为一个总文档。

## 默认输入

- 视频参考表：`/Volumes/黎鑿/4.1 AEJMC/视频/reference.csv`
- 视频目录：`/Volumes/黎鑿/4.1 AEJMC/视频/douyin`
- 输出目录：`/Volumes/黎鑿/4.1 AEJMC/提取视频文本/output`

## API 约定

当前程序按阿里云官方文档里的 **DashScope SDK + 北京区 WebSocket 接入点** 写：

- 北京区 websocket url：`wss://dashscope.aliyuncs.com/api-ws/v1/inference`
- 默认模型：`fun-asr-realtime`

环境变量：

```bash
export DASHSCOPE_API_KEY="..."
export DASHSCOPE_BASE_WEBSOCKET_API_URL="wss://dashscope.aliyuncs.com/api-ws/v1/inference"
export DASHSCOPE_TRANSCRIBE_MODEL="fun-asr-realtime"
```

和你给的示例一致，程序会从 `DASHSCOPE_API_KEY` 读取北京区百炼密钥，不再读取其他转写服务的 key 名称。

重要：

- 当前版本已经不需要公网音频 URL。
- 程序会先在本地抽出 `mp3`，再直接把**本地音频文件**送进 DashScope 识别。
- 所以你现在只需要准备 `DASHSCOPE_API_KEY`。

## 安装

```bash
python3 -m venv "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv"
"/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv/bin/python" -m pip install -r "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/requirements.txt"
```

系统需要：

- `ffmpeg`

## 运行

全量跑：

```bash
"/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv/bin/python" \
  "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/main.py"
```

先随机抽 20 条测试：

```bash
"/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv/bin/python" \
  "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/main.py" \
  --sample-size 20
```

只跑前 10 条：

```bash
"/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv/bin/python" \
  "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/main.py" \
  --limit 10
```

覆盖已存在转写：

```bash
"/Volumes/黎鑿/4.1 AEJMC/提取视频文本/.venv/bin/python" \
  "/Volumes/黎鑿/4.1 AEJMC/提取视频文本/main.py" \
  --overwrite-transcript
```

## 输出结构

```text
提取视频文本/
  output/
    audio_files/
      7587736919656779023.mp3
    transcripts/
      7587736919656779023/
        7587736919656779023.json
        7587736919656779023.txt
        7587736919656779023.md
    merged_transcripts.md
    failed_videos.csv
```

## 说明

- 当前版本提取的是**视频语音转文本**，不是 OCR。
- `md` 文件里会带上视频 ID、作者、标题和全文文本，并记录本地音频路径。
- 如果某条失败，会记到 `failed_videos.csv`，不会中断整批处理。
