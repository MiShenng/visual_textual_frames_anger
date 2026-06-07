# Short Video Crawler

当前实现的是一个 `抖音优先` 的短视频爬虫系统，已经包含：

- FastAPI 控制 API
- Typer CLI
- MySQL/SQLite 兼容的 SQLAlchemy 存储层
- 任务模型、视频表、评论表、账号表、代理表、事件表
- 账号/代理熔断与冷却逻辑
- 搜索任务与评论任务执行链路
- 简单卡片式 Web 面板
- 抖音/TikTok 适配器标准化层
- 第三方 API 兜底接口

当前本地视频存储目录可以通过环境变量配置：

- `CRAWLER_VIDEO_STORE_DIR`
- `CRAWLER_COMMENT_STORE_DIR`
- `CRAWLER_SNAPSHOT_DIR`

请求侧风控参数（代理轮换/熔断/并发）可以通过以下环境变量调整：

- `CRAWLER_REQUEST_RETRY_MAX_ATTEMPTS`：单次请求最大重试次数（默认 `3`）
- `CRAWLER_REQUEST_RETRY_BACKOFF_MS`：重试退避基础时长，毫秒（默认 `500`）
- `CRAWLER_REQUEST_PROXY_SWITCH_ATTEMPTS`：单次业务调用内允许切换代理的次数（默认 `3`）
- `CRAWLER_REQUEST_MAX_CONCURRENCY`：请求并发上限（默认 `2`）

建议起步参数（更稳、触发风控概率更低）：

- `CRAWLER_REQUEST_MAX_CONCURRENCY=1~2`
- `CRAWLER_REQUEST_PROXY_SWITCH_ATTEMPTS=3~5`
- `CRAWLER_REQUEST_RETRY_MAX_ATTEMPTS=2~3`
- `CRAWLER_REQUEST_RETRY_BACKOFF_MS=500~1200`

## 当前状态

已完成：

- 可运行服务与 CLI
- 数据模型与任务流
- Playwright 登录态采集与复用
- 抖音搜索、一级评论、二级回复抓取链路
- 视频下载脚本
- 单元测试
- 远端部署脚本与 systemd 服务模板

限制：

- TikTok provider 保留接口形状，但未作为本文数据采集链路使用。
- 抓取效果依赖平台实时风控、登录态、代理质量和页面接口变化。
- 登录态文件、数据库、原始评论 JSON、视频文件和日志不应提交到公开仓库。

## 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
uvicorn app.api.main:app --reload --port 8080
```

如果你要在本地把视频文件和评论文件统一放到项目内运行目录，可以在 `.env` 里设置：

```bash
CRAWLER_VIDEO_STORE_DIR=data/raw/videos_source
CRAWLER_COMMENT_STORE_DIR=data/raw/comment_json_source
```

程序启动时会自动创建缺失目录。

打开：

```text
http://127.0.0.1:8080
```

## CLI 示例

```bash
.venv/bin/python -m app.cli.main accounts capture-douyin --label main
.venv/bin/python -m app.cli.main accounts import --platform douyin --label main --state-file playwright_states/douyin_main.json
.venv/bin/python -m app.cli.main proxies import-source --source-name the_speedx_http --limit 100
.venv/bin/python -m app.cli.main proxies import-ipproxypool --base-url http://127.0.0.1:8000 --limit 100 --types 0 --protocol 0 --country 国内
.venv/bin/python -m app.cli.main jobs search --platform douyin --mode keyword --query 新能源 --limit 100
.venv/bin/python -m app.cli.main jobs comments --platform douyin --video-id 123456
```

如果抖音网页直接拒绝脚本化登录，优先使用 `accounts capture-douyin`。
这个命令会打开一个可见浏览器窗口，你手动登录成功后回终端按回车，程序会把登录态保存到 `playwright_states/`，随后可直接用于抓取。

账号管理的含义：

- `账号` 不是保存账号密码
- `账号` 是一份浏览器登录态文件，例如 `playwright_states/douyin_main.json`
- 导入后，系统抓取任务会优先复用这份登录态去访问抖音
- 如果没有导入账号，很多接口会拿不到数据，或者直接被拒绝
- `Playwright` 的作用是带着完整浏览器上下文访问抖音，比单独手填 cookie 更稳

评论抓取策略：

- 搜索抓到视频后，会自动继续抓该批视频的一级评论和二级回复
- 评论文本会直接写入数据库，不需要等到最后一次性导出
- 每个视频会额外导出一个独立评论文件到 `3.21comment_data/<platform>/<video_id>.json`
- 评论文件里会区分 `一级评论` / `二级评论`，二级评论会标注它回复的是哪条一级评论
- 视频文件和评论文件使用同一套 `<video_id>` 命名，快照里的 `video_comment_map.csv` 会额外记录两边路径与存在状态
- 系统还会每隔 30 分钟把当前 `jobs/videos/comments` 快照导出到 `data/snapshots/`
- 页面里的“补抓评论”只是失败补救入口，不是主流程

补充说明：

- `jobs search` / `jobs comments` 会抓视频元数据和评论，但不会自动下载 mp4 文件
- 真正的视频文件下载仍然通过 `videos download` 执行
- 下载后的视频文件路径会是 `3.21video_data/<platform>/<video_id>.mp4`，与评论文件一一对应

公开代理池：

- 已内置 4 个 GitHub 原始代理源，可直接从网页或 CLI 导入
- 也支持对接独立部署的 `IPProxyPool` API，把它当成一个持续供给的代理来源
- 首轮建议先小批量导入，例如 `50-200` 条，再观察成功率
- 免费公开代理波动很大，适合冷启动和验证，不适合长期稳定生产
- 当前代理管理支持：导入、来源识别、批量验证、清理失效代理

`IPProxyPool` 接入方式：

- 先单独把 `qiyeboy/IPProxyPool` 跑起来，默认地址通常是 `http://127.0.0.1:8000`
- 当前项目支持通过网页或 CLI 调用它的 `GET /` API 拉取代理
- 可传的筛选参数与原项目保持一致：`types / protocol / count / country / area`
- 当前默认配置项：
  - `CRAWLER_IPPROXYPOOL_BASE_URL`
  - `CRAWLER_IPPROXYPOOL_TYPES`
  - `CRAWLER_IPPROXYPOOL_PROTOCOL`
  - `CRAWLER_IPPROXYPOOL_COUNTRY`
  - `CRAWLER_IPPROXYPOOL_AREA`

时间筛选：

- `start_time` 可选
- `end_time` 可选
- 支持 `YYYY-MM-DD` 和 ISO 时间格式
- 旧的 `time_range=start:end` 仍然兼容

## 数据库

- 默认：`sqlite:///./crawler.sqlite3`
- 服务器部署：把 `.env.example` 复制为 `.env`，并把 `CRAWLER_DATABASE_URL` 改成 MySQL 8

## 服务器部署

当前仓库已经自带远端部署脚本，会把项目同步到服务器的 `~/crawler_app`，创建 `.venv`，并安装一个 `systemd` 服务：

```bash
bash crawler_deploy/deploy_to_remote.sh <ssh-host-alias-or-user@host>
```

部署完成后，服务名是：

```text
short-video-crawler
```

常用命令：

```bash
ssh <ssh-host-alias-or-user@host> 'sudo systemctl restart short-video-crawler'
ssh <ssh-host-alias-or-user@host> 'sudo systemctl status short-video-crawler --no-pager'
ssh <ssh-host-alias-or-user@host> 'tail -n 100 /home/ubuntu/crawler_app/crawler.log'
```

默认监听：

```text
http://<server-ip>:8080
```

如果你要切到 MySQL 8，只需要在服务器上修改：

```text
/home/ubuntu/crawler_app/.env
```

把 `CRAWLER_DATABASE_URL` 改成真实 MySQL DSN，然后重启服务。

## 本项目采集链路

- 关键词检索：`scripts/run_keyword_batch.py`
- 评论补抓：`scripts/backfill_keep_zero_comments.py`
- 样本筛选：`scripts/curate_topic_videos.py`
- 视频下载：`scripts/download_final_keep_videos.py`
- 抖音 provider：`app/platforms/playwright_provider.py`
