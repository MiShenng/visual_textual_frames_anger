from __future__ import annotations

import argparse
import base64
import csv
import json
import time
from pathlib import Path

from app.platforms.playwright_provider import PlaywrightProviderClient
from app.platforms.schemas import CrawlContext


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CSV = Path("data/processed/video_level_final_449.csv")
DEFAULT_TARGET_DIR = Path("data/raw/videos_source/douyin")
DEFAULT_STATUS_PATH = Path("outputs/crawler/download_logs/final_keep_chunked_download_status.json")
DEFAULT_FAILED_CSV = Path("outputs/crawler/download_logs/final_keep_chunked_download_failed.csv")
DEFAULT_STATE_PATH = "playwright_states/douyin_main.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download curated Douyin videos via the logged-in Playwright page session."
    )
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--failed-csv", type=Path, default=DEFAULT_FAILED_CSV)
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH)
    parser.add_argument("--goto-timeout-ms", type=int, default=45000)
    parser.add_argument("--video-timeout-ms", type=int, default=45000)
    parser.add_argument("--src-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--wait-after-play-ms", type=int, default=1200)
    parser.add_argument("--fetch-timeout-ms", type=int, default=45000)
    parser.add_argument("--chunk-size", type=int, default=1024 * 1024)
    parser.add_argument("--reopen-every", type=int, default=20)
    parser.add_argument("--retry-passes", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def load_selected_video_ids(source_csv: Path, limit: int | None = None) -> list[str]:
    selected_ids: list[str] = []
    with source_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            video_id = (row.get("platform_video_id") or "").strip()
            if video_id and video_id not in selected_ids:
                selected_ids.append(video_id)
            if limit is not None and len(selected_ids) >= limit:
                break
    return selected_ids


def unresolved_failed_ids(
    failed_reasons: dict[str, str], target_dir: Path, attempts: dict[str, int]
) -> list[str]:
    retry_ids: list[str] = []
    for video_id in failed_reasons:
        target = target_dir / f"{video_id}.mp4"
        if target.exists() and target.stat().st_size > 0:
            continue
        if attempts.get(video_id, 0) <= 0:
            continue
        retry_ids.append(video_id)
    return retry_ids


def write_failed_csv(
    failed_csv: Path, failed_reasons: dict[str, str], attempts: dict[str, int], target_dir: Path
) -> None:
    failed_csv.parent.mkdir(parents=True, exist_ok=True)
    with failed_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["platform_video_id", "attempts", "reason"])
        writer.writeheader()
        for video_id in unresolved_failed_ids(failed_reasons, target_dir, attempts):
            writer.writerow(
                {
                    "platform_video_id": video_id,
                    "attempts": attempts.get(video_id, 0),
                    "reason": failed_reasons[video_id],
                }
            )


def video_target_path(target_dir: Path, video_id: str) -> Path:
    return target_dir / f"{video_id}.mp4"


def existing_file_count(target_dir: Path) -> int:
    return len([path for path in target_dir.glob("*.mp4") if path.is_file() and not path.name.startswith("._")])


def is_http_src(value: object) -> bool:
    return isinstance(value, str) and value.startswith("http")


def open_session(provider: PlaywrightProviderClient, ctx: CrawlContext):
    manager = provider._session(ctx)
    session = manager.__enter__()
    return manager, session


def close_session(manager, session) -> None:
    try:
        manager.__exit__(None, None, None)
    except Exception:
        try:
            session.close()
        except Exception:
            pass


def resolve_video_src(
    page,
    video_id: str,
    goto_timeout_ms: int,
    video_timeout_ms: int,
    src_timeout_seconds: float,
    wait_after_play_ms: int,
) -> str:
    page.goto(
        f"https://www.douyin.com/video/{video_id}",
        wait_until="commit",
        timeout=goto_timeout_ms,
    )
    page.wait_for_selector("video", state="attached", timeout=video_timeout_ms)

    deadline = time.monotonic() + src_timeout_seconds
    last_state: dict[str, object] | None = None
    while time.monotonic() < deadline:
        state = page.evaluate(
            """
            () => {
              const video = document.querySelector('video');
              if (!video) {
                return {ok: false, reason: 'no-video'};
              }
              try {
                video.muted = true;
                video.playsInline = true;
                video.autoplay = true;
                const playResult = video.play();
                if (playResult && typeof playResult.catch === 'function') {
                  playResult.catch(() => {});
                }
              } catch (error) {}
              try { video.click(); } catch (error) {}
              return {
                ok: Boolean(video.currentSrc),
                currentSrc: video.currentSrc || null,
                readyState: video.readyState,
                hidden: video.offsetParent === null,
                display: getComputedStyle(video).display,
                visibility: getComputedStyle(video).visibility,
              };
            }
            """
        )
        last_state = state
        current_src = state.get("currentSrc")
        if state.get("ok") and is_http_src(current_src):
            return current_src
        page.wait_for_timeout(wait_after_play_ms)
    raise RuntimeError(f"video_src_timeout:{video_id}:{last_state}")


def fetch_video_meta(page, url: str, fetch_timeout_ms: int) -> tuple[int, str]:
    meta = page.evaluate(
        """
        async ({url, timeoutMs}) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort('meta-timeout'), timeoutMs);
          try {
            const res = await fetch(url, {
              headers: { Range: 'bytes=0-0' },
              credentials: 'omit',
              signal: controller.signal,
            });
            return {
              ok: res.ok,
              status: res.status,
              contentRange: res.headers.get('content-range'),
            };
          } catch (error) {
            return {
              ok: false,
              status: null,
              error: String(error),
              contentRange: null,
            };
          } finally {
            clearTimeout(timer);
          }
        }
        """,
        {"url": url, "timeoutMs": fetch_timeout_ms},
    )
    if not meta.get("ok"):
        raise RuntimeError(f"meta_fetch_failed:{meta}")
    content_range = meta.get("contentRange") or ""
    if "/" not in content_range:
        raise RuntimeError(f"content_range_missing:{content_range}")
    total = int(content_range.split("/")[-1])
    return total, content_range


def fetch_chunk_base64(page, url: str, start: int, end: int, fetch_timeout_ms: int) -> bytes:
    payload = page.evaluate(
        """
        async ({url, start, end, timeoutMs}) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort('chunk-timeout'), timeoutMs);
          try {
            const res = await fetch(url, {
              headers: { Range: `bytes=${start}-${end}` },
              credentials: 'omit',
              signal: controller.signal,
            });
            const buf = await res.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            const step = 0x8000;
            for (let i = 0; i < bytes.length; i += step) {
              binary += String.fromCharCode(...bytes.subarray(i, i + step));
            }
            return {
              ok: res.ok,
              status: res.status,
              len: bytes.length,
              base64: btoa(binary),
            };
          } catch (error) {
            return {
              ok: false,
              status: null,
              len: 0,
              error: String(error),
              base64: '',
            };
          } finally {
            clearTimeout(timer);
          }
        }
        """,
        {"url": url, "start": start, "end": end, "timeoutMs": fetch_timeout_ms},
    )
    if not payload.get("ok"):
        raise RuntimeError(f"chunk_fetch_failed:{payload}")
    return base64.b64decode(payload["base64"])


def download_single_video(
    page,
    video_id: str,
    target_dir: Path,
    goto_timeout_ms: int,
    video_timeout_ms: int,
    src_timeout_seconds: float,
    wait_after_play_ms: int,
    fetch_timeout_ms: int,
    chunk_size: int,
    progress_callback=None,
) -> int:
    target = video_target_path(target_dir, video_id)
    temp = target.with_suffix(target.suffix + ".part")
    if temp.exists():
        temp.unlink()

    if progress_callback:
        progress_callback(step="resolve_src")
    src = resolve_video_src(
        page=page,
        video_id=video_id,
        goto_timeout_ms=goto_timeout_ms,
        video_timeout_ms=video_timeout_ms,
        src_timeout_seconds=src_timeout_seconds,
        wait_after_play_ms=wait_after_play_ms,
    )
    if progress_callback:
        progress_callback(step="fetch_meta")
    total, _ = fetch_video_meta(page, src, fetch_timeout_ms=fetch_timeout_ms)
    downloaded_bytes = 0
    with temp.open("wb") as handle:
        start = 0
        chunk_index = 0
        while start < total:
            end = min(start + chunk_size - 1, total - 1)
            handle.write(fetch_chunk_base64(page, src, start, end, fetch_timeout_ms=fetch_timeout_ms))
            downloaded_bytes += end - start + 1
            chunk_index += 1
            if progress_callback and (chunk_index == 1 or chunk_index % 10 == 0 or downloaded_bytes == total):
                progress_callback(
                    step="fetch_chunks",
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total,
                    chunk_index=chunk_index,
                )
            start = end + 1
    if downloaded_bytes != total:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"size_mismatch:{downloaded_bytes}!={total}")
    temp.replace(target)
    return downloaded_bytes


def main() -> int:
    args = parse_args()
    selected_ids = load_selected_video_ids(args.source_csv, limit=args.limit)
    target_dir = args.target_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    args.status_path.parent.mkdir(parents=True, exist_ok=True)

    status = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_csv": str(args.source_csv),
        "target_root": str(target_dir),
        "selected": len(selected_ids),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "current_index": 0,
        "current_video_id": None,
        "last_completed_video_id": None,
        "retry_pass": 0,
        "phase": "initial",
        "current_step": None,
        "current_downloaded_bytes": 0,
        "current_total_bytes": 0,
        "current_chunk_index": 0,
        "existing_mp4_count": existing_file_count(target_dir),
    }
    failed_reasons: dict[str, str] = {}
    attempts: dict[str, int] = {}

    def write_status() -> None:
        status["existing_mp4_count"] = existing_file_count(target_dir)
        args.status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        write_failed_csv(args.failed_csv, failed_reasons, attempts, target_dir)

    provider = PlaywrightProviderClient()
    ctx = CrawlContext(login_state_path=args.state_path)
    manager, session = open_session(provider, ctx)
    write_status()
    print(json.dumps({"stage": "download_start", "selected": len(selected_ids)}, ensure_ascii=False), flush=True)

    def process(video_ids: list[str], phase: str, retry_pass: int) -> None:
        nonlocal manager, session
        for index, video_id in enumerate(video_ids, start=1):
            status["phase"] = phase
            status["retry_pass"] = retry_pass
            status["current_index"] = index
            status["current_video_id"] = video_id
            status["current_step"] = "starting"
            status["current_downloaded_bytes"] = 0
            status["current_total_bytes"] = 0
            status["current_chunk_index"] = 0
            target = video_target_path(target_dir, video_id)
            if target.exists() and target.stat().st_size > 0:
                status["skipped"] += 1
                status["last_completed_video_id"] = video_id
                write_status()
                continue
            attempts[video_id] = attempts.get(video_id, 0) + 1
            if index > 1 and (index - 1) % max(1, args.reopen_every) == 0:
                close_session(manager, session)
                manager, session = open_session(provider, ctx)
            try:
                def progress_callback(*, step: str, downloaded_bytes: int = 0, total_bytes: int = 0, chunk_index: int = 0) -> None:
                    status["current_step"] = step
                    status["current_downloaded_bytes"] = downloaded_bytes
                    status["current_total_bytes"] = total_bytes
                    status["current_chunk_index"] = chunk_index
                    write_status()

                downloaded_bytes = download_single_video(
                    page=session.page,
                    video_id=video_id,
                    target_dir=target_dir,
                    goto_timeout_ms=args.goto_timeout_ms,
                    video_timeout_ms=args.video_timeout_ms,
                    src_timeout_seconds=args.src_timeout_seconds,
                    wait_after_play_ms=args.wait_after_play_ms,
                    fetch_timeout_ms=args.fetch_timeout_ms,
                    chunk_size=args.chunk_size,
                    progress_callback=progress_callback,
                )
                status["downloaded"] += 1
                status["last_completed_video_id"] = video_id
                status["current_step"] = "completed"
                status["current_downloaded_bytes"] = downloaded_bytes
                status["current_total_bytes"] = downloaded_bytes
                failed_reasons.pop(video_id, None)
                print(
                    json.dumps(
                        {
                            "stage": "video_downloaded",
                            "phase": phase,
                            "retry_pass": retry_pass,
                            "video_id": video_id,
                            "bytes": downloaded_bytes,
                            "downloaded": status["downloaded"],
                            "skipped": status["skipped"],
                            "failed": status["failed"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:
                status["failed"] += 1
                status["current_step"] = "failed"
                failed_reasons[video_id] = str(exc)
                print(
                    json.dumps(
                        {
                            "stage": "video_failed",
                            "phase": phase,
                            "retry_pass": retry_pass,
                            "video_id": video_id,
                            "error": str(exc),
                            "failed": status["failed"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                close_session(manager, session)
                manager, session = open_session(provider, ctx)
            write_status()

    process(selected_ids, phase="initial", retry_pass=0)

    for retry_pass in range(1, max(0, args.retry_passes) + 1):
        retry_ids = unresolved_failed_ids(failed_reasons, target_dir, attempts)
        if not retry_ids:
            break
        print(
            json.dumps(
                {
                    "stage": "retry_start",
                    "retry_pass": retry_pass,
                    "retry_count": len(retry_ids),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        process(retry_ids, phase="retry", retry_pass=retry_pass)

    close_session(manager, session)
    status["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_status()
    print(json.dumps({"stage": "download_end", **status}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
