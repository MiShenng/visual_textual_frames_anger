from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import ensure_runtime_paths, get_settings
from app.core.enums import JobStatus, Platform, QueryType
from app.storage.base import Base
from app.storage.models import Account, Comment, CrawlEvent, CrawlJob, ProxyEndpoint, Video
from app.storage.session import SessionLocal, engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run keyword search jobs sequentially and stream crawler events."
    )
    parser.add_argument("--platform", default="douyin", choices=[item.value for item in Platform])
    parser.add_argument("--mode", default="keyword", choices=[item.value for item in QueryType])
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--time-range", required=True)
    parser.add_argument("--report-seconds", type=int, default=300)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("keywords", nargs="+")
    return parser.parse_args()


class BatchLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, message: str, *, payload: dict | None = None) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {message}"
        if payload is not None:
            line = f"{line} | {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        with self._lock:
            print(line, flush=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _with_db_retry(operation, attempts: int = 5, sleep_seconds: float = 1.0):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except OperationalError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            time.sleep(sleep_seconds * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("db retry failed without exception")


def current_counts() -> dict[str, int]:
    def _operation() -> dict[str, int]:
        with SessionLocal() as db:
            return {
                "jobs": int(db.scalar(select(func.count(CrawlJob.id))) or 0),
                "videos": int(db.scalar(select(func.count(Video.id))) or 0),
                "comments": int(db.scalar(select(func.count(Comment.id))) or 0),
                "accounts": int(db.scalar(select(func.count(Account.id))) or 0),
                "proxies": int(db.scalar(select(func.count(ProxyEndpoint.id))) or 0),
            }

    return _with_db_retry(_operation)


def running_job_rows() -> list[dict]:
    def _operation() -> list[dict]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(CrawlJob).where(CrawlJob.status == JobStatus.RUNNING).order_by(CrawlJob.id.asc())
            ).all()
            return [
                {
                    "job_id": item.id,
                    "job_type": item.job_type.value,
                    "platform": item.platform.value,
                    "query": item.query,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in rows
            ]

    return _with_db_retry(_operation)


def start_event_monitor(
    logger: BatchLogger,
    report_seconds: int,
    poll_seconds: int,
    stop_event: threading.Event,
) -> threading.Thread:
    def _runner() -> None:
        last_event_id = _with_db_retry(
            lambda: _read_last_event_id(),
        )
        last_report_at = 0.0
        while not stop_event.is_set():
            try:
                events = _with_db_retry(lambda: _read_new_events(last_event_id))
                for event in events:
                    last_event_id = event.id
                    logger.log(
                        f"event={event.event_type} level={event.level} job_id={event.job_id}",
                        payload={
                            "message": event.message,
                            "platform": event.platform.value if event.platform else None,
                            "payload": event.payload,
                        },
                    )
            except Exception as exc:
                logger.log("monitor_error", payload={"error": repr(exc)})

            now = time.monotonic()
            if last_report_at == 0.0 or now - last_report_at >= report_seconds:
                try:
                    logger.log(
                        "periodic_report",
                        payload={
                            "counts": current_counts(),
                            "running_jobs": running_job_rows(),
                        },
                    )
                except Exception as exc:
                    logger.log("monitor_error", payload={"error": repr(exc)})
                last_report_at = now
            stop_event.wait(max(1, poll_seconds))

    thread = threading.Thread(target=_runner, name="crawl-event-monitor", daemon=True)
    thread.start()
    return thread


def _read_last_event_id() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.max(CrawlEvent.id))) or 0)


def _read_new_events(last_event_id: int) -> list[CrawlEvent]:
    with SessionLocal() as db:
        return db.scalars(
            select(CrawlEvent)
            .where(CrawlEvent.id > last_event_id)
            .order_by(CrawlEvent.id.asc())
        ).all()


def main() -> int:
    args = parse_args()
    ensure_runtime_paths()
    Base.metadata.create_all(bind=engine)
    settings = get_settings()

    log_dir = Path(args.log_dir)
    log_path = log_dir / f"batch_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger = BatchLogger(log_path)

    logger.log(
        "batch_start",
        payload={
            "platform": args.platform,
            "mode": args.mode,
            "limit": args.limit,
            "time_range": args.time_range,
            "keywords": args.keywords,
            "database_url": settings.database_url,
            "video_store_dir": str(settings.video_store_dir),
            "comment_store_dir": str(settings.comment_store_dir),
            "request_max_concurrency": settings.request_max_concurrency,
            "request_proxy_switch_attempts": settings.request_proxy_switch_attempts,
            "request_retry_backoff_ms": settings.request_retry_backoff_ms,
            "anti_crawl_pause_seconds": settings.anti_crawl_pause_seconds,
        },
    )

    counts = current_counts()
    if counts["accounts"] == 0:
        logger.log("warning_no_account", payload={"message": "未导入登录态，搜索与评论完整性会明显下降"})
    if counts["proxies"] == 0:
        logger.log("warning_no_proxy", payload={"message": "当前没有代理，将以直连方式运行"})

    stop_event = threading.Event()
    monitor = start_event_monitor(
        logger=logger,
        report_seconds=max(1, args.report_seconds),
        poll_seconds=max(1, args.poll_seconds),
        stop_event=stop_event,
    )

    platform = Platform(args.platform)
    mode = QueryType(args.mode)
    try:
        for index, keyword in enumerate(args.keywords, start=1):
            started_at = time.monotonic()
            logger.log(
                f"job_start index={index}/{len(args.keywords)}",
                payload={"keyword": keyword},
            )
            try:
                command = [
                    sys.executable,
                    "-m",
                    "app.cli.main",
                    "jobs",
                    "search",
                    platform.value,
                    "--mode",
                    mode.value,
                    "--query",
                    keyword,
                    "--limit",
                    str(args.limit),
                    "--time-range",
                    args.time_range,
                ]
                logger.log("job_command", payload={"keyword": keyword, "command": command})
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    cwd=Path.cwd(),
                )
                output = (completed.stdout or "").strip()
                error_output = (completed.stderr or "").strip()
                job_id = None
                if output.startswith("job_id="):
                    for token in output.split():
                        if token.startswith("job_id="):
                            try:
                                job_id = int(token.split("=", 1)[1])
                            except ValueError:
                                job_id = None
                            break
                with SessionLocal() as db:
                    if job_id is not None:
                        job = db.get(CrawlJob, job_id)
                    else:
                        job = None
                    logger.log(
                        f"job_end index={index}/{len(args.keywords)}",
                        payload={
                            "keyword": keyword,
                            "returncode": completed.returncode,
                            "stdout": output,
                            "stderr": error_output,
                            "job_id": job.id if job else None,
                            "status": job.status.value if job else None,
                            "error_summary": job.error_summary if job else None,
                            "elapsed_seconds": round(time.monotonic() - started_at, 2),
                            "counts": current_counts(),
                        },
                    )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.log(
                    f"job_exception index={index}/{len(args.keywords)}",
                    payload={
                        "keyword": keyword,
                        "error": repr(exc),
                        "elapsed_seconds": round(time.monotonic() - started_at, 2),
                    },
                )
        logger.log("batch_end", payload={"counts": current_counts()})
        return 0
    except KeyboardInterrupt:
        logger.log("batch_interrupted", payload={"counts": current_counts()})
        return 130
    finally:
        stop_event.set()
        monitor.join(timeout=max(1, args.poll_seconds) + 1)


if __name__ == "__main__":
    raise SystemExit(main())
