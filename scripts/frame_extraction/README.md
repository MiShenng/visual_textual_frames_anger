# 视频切片与代表帧

脚本按 1 fps 抽帧，以相邻帧 pHash 汉明距离划分连续片段，并以拉普拉斯方差选择每段代表帧。`remove=1` 的视频会被排除。

默认路径从仓库根目录解析：

- 输入表：`data/raw/videos_source/final_keep_videos_round2_flat.csv`
- 视频目录：`data/raw/videos_source/douyin`
- 输出目录：`outputs/frame_extraction`

## 环境与运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/frame_extraction/requirements.txt
.venv/bin/python scripts/frame_extraction/video_slice_pipeline.py --process-all --workers 8
```

系统需提供 `ffmpeg` 和 `ffprobe`。不加 `--process-all` 时按 `--sample-size` 和 `--seed` 抽样。全部参数见：

```bash
.venv/bin/python scripts/frame_extraction/video_slice_pipeline.py --help
```

每次运行在 `outputs/frame_extraction/切片结果/<run_name>/` 写出样本表、运行汇总、视频汇总、失败记录，以及每条视频的帧表、分段表和代表帧。

测试：

```bash
cd scripts/frame_extraction
python3 -m unittest -v test_video_slice_pipeline.py
```
