# Short Video Crawler

该目录保存本文使用的抖音关键词检索、评论采集、样本筛选和视频下载代码，并提供 FastAPI、CLI、SQLite/MySQL 存储与 Playwright 登录态支持。TikTok 接口未用于本文数据采集。

## 环境与启动

```bash
cd scripts/crawler
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.api.main:app --port 8080
```

默认数据库为 `sqlite:///./crawler.sqlite3`。本地文件目录通过以下环境变量配置：

- `CRAWLER_VIDEO_STORE_DIR`
- `CRAWLER_COMMENT_STORE_DIR`
- `CRAWLER_SNAPSHOT_DIR`
- `CRAWLER_DATABASE_URL`

登录态通过 CLI 创建或导入；仓库不保存账号密码：

```bash
.venv/bin/python -m app.cli.main accounts capture-douyin --label main
.venv/bin/python -m app.cli.main accounts import --platform douyin --label main --state-file playwright_states/douyin_main.json
```

任务命令：

```bash
.venv/bin/python -m app.cli.main jobs search --platform douyin --mode keyword --query 新能源 --limit 100
.venv/bin/python -m app.cli.main jobs comments --platform douyin --video-id 123456
```

本文采集脚本：

- `scripts/run_keyword_batch.py`：关键词检索。
- `scripts/backfill_keep_zero_comments.py`：评论补抓。
- `scripts/curate_topic_videos.py`：样本筛选。
- `scripts/download_final_keep_videos.py`：视频下载。

平台页面和风控规则可能变化。运行时须遵守平台条款、隐私要求和研究伦理；登录态、数据库、评论 JSON、视频和日志不得提交到公开仓库。

测试：

```bash
.venv/bin/python -m pytest -q
```
