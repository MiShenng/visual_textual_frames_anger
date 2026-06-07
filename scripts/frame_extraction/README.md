# 视频切片程序

这套程序对应论文里的视觉框架预处理阶段，当前只做以下 4 步：

1. 从筛选后的视频表里随机抽样视频。
2. 对每条视频按 `1 fps` 抽帧。
3. 对相邻帧计算 `pHash`，按汉明距离阈值做连续片段归并。
4. 对每个片段用拉普拉斯方差选出最清晰的代表帧。

当前版本**不接多模态模型**，先把“抽帧、去重、代表帧、时间轴映射”跑通。

## 默认输入

- 视频表：`data/raw/videos_source/final_keep_videos_round2_flat.csv`
- 视频目录：`data/raw/videos_source/douyin`
- 输出目录：`outputs/frame_extraction`

程序会自动忽略 `remove=1` 的行。

## 环境

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/frame_extraction/requirements.txt
```

系统还需要：

- `ffmpeg`
- `ffprobe`

## 跑 20 条随机测试

```bash
.venv/bin/python scripts/frame_extraction/video_slice_pipeline.py
```

## 跑全量

```bash
.venv/bin/python scripts/frame_extraction/video_slice_pipeline.py \
  --process-all \
  --workers 8
```

## 常用参数

```bash
--sample-size 20
--seed 20260323
--fps 1
--phash-threshold 12
--workers 8
--run-name custom_name
```

## 输出结构

每次运行会在 `视频切片/` 下生成一个新的 run 文件夹，例如：

```text
视频切片/
  切片结果/
    sample20_20260323_190000_seed20260323/
      sample_videos.csv
      run_summary.json
      video_summary.csv
      failed_videos.csv
      videos/
        7587736919656779023/
          raw_frames/
          representative_frames/
          frames.csv
          segments.csv
          segments.json
```

另外会在 `视频切片/latest_run.json` 写入最近一次运行的位置。

如果某条视频本身损坏或无法抽帧，程序不会中断整轮任务，而是把失败记录写到 `failed_videos.csv/json`，继续补足样本。
