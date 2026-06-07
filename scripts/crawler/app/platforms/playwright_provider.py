import re
import json
import subprocess
import random
import time
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx
from app.core.config import get_settings
from app.core.errors import AntiCrawlDetectedError
from app.core.enums import Platform, QueryType
from app.platforms.provider import ProviderClient
from app.platforms.schemas import CrawlContext

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Response


SEARCH_PATH = "/aweme/v1/web/general/search/single/"
SEARCH_STREAM_PATH = "/aweme/v1/web/general/search/stream/"
COMMENTS_PATH = "/aweme/v1/web/comment/list/"
REPLIES_PATH = "/aweme/v1/web/comment/list/reply/"
REPLY_BUTTON_PATTERN = re.compile(r"(展开|查看|更多).{0,8}回复")
SEARCH_COUNT = 15
COMMENTS_COUNT = 20
ANTI_CRAWL_KEYWORDS = (
    "captcha",
    "verify",
    "verify your identity",
    "risk",
    "forbidden",
    "too many requests",
    "验证码",
    "风控",
    "访问受限",
    "操作频繁",
    "请求过于频繁",
)


@dataclass(slots=True)
class _CapturedResponse:
    url: str
    payload: dict


@dataclass(slots=True)
class _ResponseCollector:
    patterns: tuple[str, ...]
    events: list[_CapturedResponse] = field(default_factory=list)

    def bind(self, page: "Page") -> None:
        def _handler(response: "Response") -> None:
            url = response.url
            if not any(pattern in url for pattern in self.patterns):
                return
            try:
                payload = response.json()
            except Exception:
                payload = _parse_chunked_json_payload(response)
                if payload is None:
                    return
            self.events.append(_CapturedResponse(url=url, payload=payload))

        page.on("response", _handler)

    def payloads_for_path(self, path: str) -> list[dict]:
        return [item.payload for item in self.events if path in item.url]


@dataclass(slots=True)
class _BrowserSession:
    playwright: "Playwright"
    browser: "Browser"
    context: "BrowserContext"
    page: "Page"

    def close(self) -> None:
        self.context.close()
        self.browser.close()
        self.playwright.stop()


@dataclass(slots=True)
class _StateRuntime:
    cookie_header: str
    webid: str
    xmst: str
    user_agent: str


def _parse_proxy_config(proxy_url: str | None) -> dict | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return {"server": proxy_url}
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    proxy: dict[str, str] = {"server": server}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


def _query_param(url: str, key: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def _normalize_search_payload(payload: dict) -> list[dict]:
    records: list[dict] = []
    for item in payload.get("data") or []:
        aweme_info = item.get("aweme_info")
        if aweme_info:
            records.append(aweme_info)
            continue
        mix_items = ((item.get("aweme_mix_info") or {}).get("mix_items") or [])
        if mix_items:
            records.append(mix_items[0])
    return records


def _parse_chunked_json_payload(response: "Response") -> dict | None:
    try:
        text = response.text()
    except Exception:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_inline_replies(comment: dict) -> list[dict]:
    replies = comment.get("reply_comment") or comment.get("reply_comments") or []
    return [reply for reply in replies if reply.get("cid") or reply.get("comment_id")]


def _normalize_comment_payload(payload: dict) -> list[dict]:
    return [
        comment
        for comment in (payload.get("comments") or [])
        if comment.get("cid") or comment.get("comment_id")
    ]


def _next_cursor(payload: dict) -> str | None:
    if not payload.get("has_more"):
        return None
    cursor = payload.get("cursor")
    if cursor is None:
        return None
    return str(cursor)


def _payload_text(payload: dict) -> str:
    values = [
        payload.get("status_msg"),
        payload.get("message"),
        payload.get("msg"),
        payload.get("description"),
        payload.get("detail"),
    ]
    return " ".join(str(item) for item in values if item).lower()


def _is_anti_crawl_payload(payload: dict) -> bool:
    text = _payload_text(payload)
    if any(keyword in text for keyword in ANTI_CRAWL_KEYWORDS):
        return True
    status_code = payload.get("status_code")
    if isinstance(status_code, int) and status_code in {4, 403, 429, 1105, 2193}:
        return True
    return False


def _fallback_webid() -> str:
    return "7618119451833304585"


def _sign_script_candidates() -> list[Path]:
    return [
        Path("vendor/douyin.js"),
        Path("/tmp/mediacrawler_repo_24635/libs/douyin.js"),
    ]


def _resolve_sign_script() -> Path:
    for candidate in _sign_script_candidates():
        if candidate.exists():
            return candidate
    raise FileNotFoundError("douyin sign script not found")


def _is_missing_sign_script(error: Exception) -> bool:
    return isinstance(error, FileNotFoundError) and str(error) == "douyin sign script not found"


def _extract_webid(local_storage: dict[str, str]) -> str:
    for key in ("SysInfo", "__tea_cache_tokens_6383", "__tea_cache_tokens_2285", "__tea_cache_tokens_3722"):
        raw = local_storage.get(key)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for candidate_key in ("webid", "user_unique_id", "web_id", "device_id"):
            value = payload.get(candidate_key)
            if value:
                return str(value)
    return _fallback_webid()


def _load_state_runtime(state_path: str, user_agent: str) -> _StateRuntime:
    payload = json.loads(Path(state_path).read_text())
    cookies = [item for item in payload.get("cookies", []) if "douyin.com" in item.get("domain", "")]
    cookie_header = "; ".join(
        f"{item['name']}={item['value']}"
        for item in cookies
        if item.get("name")
    )
    origin = next(
        (
            item
            for item in payload.get("origins", [])
            if item.get("origin") == "https://www.douyin.com"
        ),
        None,
    )
    if origin is None:
        raise ValueError("douyin origin not found in login state")
    local_storage = {
        item["name"]: item["value"]
        for item in origin.get("localStorage", [])
        if item.get("name")
    }
    xmst = str(local_storage.get("xmst") or "")
    return _StateRuntime(
        cookie_header=cookie_header,
        webid=_extract_webid(local_storage),
        xmst=xmst,
        user_agent=user_agent,
    )


class PlaywrightProviderClient(ProviderClient):
    """
    Browser-backed provider for the crawler skeleton.

    The implementation is intentionally Douyin-first. TikTok keeps the same API
    shape but remains unimplemented until the Douyin path is validated.
    """

    _semaphore_lock: Lock = Lock()
    _request_semaphore: BoundedSemaphore | None = None
    _request_semaphore_size: int | None = None

    def __init__(self) -> None:
        self.settings = get_settings()
        self._reply_cache: dict[tuple[Platform, str, str], list[dict]] = {}

    @contextmanager
    def _request_slot(self):
        max_concurrency = max(1, self.settings.request_max_concurrency)
        with self._semaphore_lock:
            if (
                self._request_semaphore is None
                or self._request_semaphore_size != max_concurrency
            ):
                self._request_semaphore = BoundedSemaphore(value=max_concurrency)
                self._request_semaphore_size = max_concurrency
            semaphore = self._request_semaphore
        if semaphore is None:
            yield
            return
        semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()

    def _sleep_with_jitter(self) -> None:
        min_ms = max(0, self.settings.request_jitter_min_ms)
        max_ms = max(min_ms, self.settings.request_jitter_max_ms)
        if max_ms <= 0:
            return
        time.sleep(random.uniform(min_ms, max_ms) / 1000.0)

    def _sleep_with_backoff(self, attempt: int) -> None:
        base_ms = max(0, self.settings.request_retry_backoff_ms)
        if base_ms <= 0:
            return
        delay_ms = base_ms * (2 ** max(0, attempt - 1))
        time.sleep((delay_ms + random.uniform(0, base_ms)) / 1000.0)

    def search(
        self,
        platform: Platform,
        query_type: QueryType,
        query: str,
        time_range: str | None,
        limit: int | None,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        if platform != Platform.DOUYIN:
            raise NotImplementedError("TikTok browser provider is not implemented yet.")
        state_path = crawl_context.login_state_path if crawl_context else None
        if state_path:
            try:
                return self._search_via_state(
                    query=query,
                    cursor=cursor,
                    limit=limit,
                    state_path=state_path,
                )
            except Exception:
                pass
        del time_range
        with self._session(crawl_context) as session:
            target = f"https://www.douyin.com/search/{quote(query.strip('#'))}?type=general"
            session.page.goto(target, wait_until="domcontentloaded")
            session.page.wait_for_timeout(1800)
            results, next_cursor = self._crawl_search_results(
                page=session.page,
                query=query,
                cursor=cursor,
                limit=limit,
            )
            return results, next_cursor

    def comments(
        self,
        platform: Platform,
        platform_video_id: str,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        if platform != Platform.DOUYIN:
            raise NotImplementedError("TikTok browser provider is not implemented yet.")
        state_path = crawl_context.login_state_path if crawl_context else None
        if state_path:
            try:
                return self._comments_via_state(platform_video_id, cursor, state_path)
            except Exception as exc:
                if not _is_missing_sign_script(exc):
                    raise
        with self._session(crawl_context) as session:
            self._goto_video_page(session.page, platform_video_id)
            payload = self._fetch_comment_payload(
                session.page,
                platform_video_id=platform_video_id,
                cursor=cursor,
            )
            if cursor in (None, "0") and not _normalize_comment_payload(payload):
                payload = self._fetch_comment_payload_via_ui(
                    session.page,
                    platform_video_id=platform_video_id,
                )
            return _normalize_comment_payload(payload), _next_cursor(payload)

    def replies(
        self,
        platform: Platform,
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None = None,
        crawl_context: CrawlContext | None = None,
    ) -> tuple[list[dict], str | None]:
        if platform != Platform.DOUYIN:
            raise NotImplementedError("TikTok browser provider is not implemented yet.")
        state_path = crawl_context.login_state_path if crawl_context else None
        if state_path:
            try:
                return self._replies_via_state(
                    platform_video_id=platform_video_id,
                    root_comment_platform_id=root_comment_platform_id,
                    cursor=cursor,
                    state_path=state_path,
                )
            except Exception as exc:
                if not _is_missing_sign_script(exc):
                    raise
        with self._session(crawl_context) as session:
            self._goto_video_page(session.page, platform_video_id)
            payload = self._fetch_reply_payload(
                session.page,
                platform_video_id=platform_video_id,
                root_comment_platform_id=root_comment_platform_id,
                cursor=cursor,
            )
            replies = _normalize_comment_payload(payload)
            self._reply_cache[(platform, platform_video_id, root_comment_platform_id)] = replies
            return replies, _next_cursor(payload)

    def _crawl_search_results(
        self,
        page: "Page",
        query: str,
        cursor: str | None,
        limit: int | None,
    ) -> tuple[list[dict], str | None]:
        seen_ids: set[str] = set()
        results: list[dict] = []
        current_cursor = cursor or "0"
        max_pages = max(0, self.settings.search_state_max_pages)
        pages = 0
        while True:
            if max_pages > 0 and pages >= max_pages:
                break
            pages += 1
            payload = self._fetch_search_payload(page, query=query, cursor=current_cursor)
            for item in _normalize_search_payload(payload):
                aweme_id = str(item.get("aweme_id") or item.get("video_id") or "")
                if not aweme_id or aweme_id in seen_ids:
                    continue
                seen_ids.add(aweme_id)
                results.append(item)
                if limit and len(results) >= limit:
                    return results[:limit], _next_cursor(payload)
            next_cursor = _next_cursor(payload)
            if not next_cursor or next_cursor == current_cursor:
                return results[:limit] if limit else results, None
            current_cursor = next_cursor
            page.wait_for_timeout(self.settings.playwright_scroll_delay_ms)
        return results[:limit] if limit else results, current_cursor

    def _fetch_search_payload(self, page: "Page", query: str, cursor: str) -> dict:
        params = {
            "search_channel": "aweme_general",
            "enable_history": "1",
            "keyword": query,
            "search_source": "tab_search",
            "query_correct_type": "1",
            "is_filter_search": "0",
            "from_group_id": "7378810571505847586",
            "offset": cursor,
            "count": str(SEARCH_COUNT),
            "need_filter_settings": "1",
            "list_type": "multi",
            "search_id": "",
        }
        return self._page_fetch_json(page, SEARCH_PATH, params)

    def _goto_video_page(self, page: "Page", platform_video_id: str) -> None:
        target = f"https://www.douyin.com/video/{platform_video_id}"
        timeout_ms = min(self.settings.playwright_timeout_ms, 15000)
        try:
            page.goto(target, wait_until="commit", timeout=timeout_ms)
        except Exception:
            current_url = str(getattr(page, "url", "") or "")
            if platform_video_id not in current_url:
                raise
        page.wait_for_timeout(1200)

    def _fetch_comment_payload(
        self,
        page: "Page",
        platform_video_id: str,
        cursor: str | None,
    ) -> dict:
        params = {
            "aweme_id": platform_video_id,
            "cursor": cursor or "0",
            "count": str(COMMENTS_COUNT),
            "item_type": "0",
        }
        return self._page_fetch_json(page, COMMENTS_PATH, params)

    def _fetch_comment_payload_via_ui(
        self,
        page: "Page",
        platform_video_id: str,
    ) -> dict:
        collector = _ResponseCollector(patterns=(COMMENTS_PATH,))
        collector.bind(page)
        self._open_comment_panel(page)
        payloads = collector.payloads_for_path(COMMENTS_PATH)
        comments: list[dict] = []
        seen_ids: set[str] = set()
        for payload in payloads:
            for item in _normalize_comment_payload(payload):
                comment_id = str(item.get("cid") or item.get("comment_id") or "")
                if not comment_id or comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)
                comments.append(item)
        return {
            "comments": comments,
            "has_more": 0,
            "cursor": 0,
        }

    def _fetch_reply_payload(
        self,
        page: "Page",
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None,
    ) -> dict:
        params = {
            "comment_id": root_comment_platform_id,
            "cursor": cursor or "0",
            "count": str(COMMENTS_COUNT),
            "item_type": "0",
            "item_id": platform_video_id,
        }
        return self._page_fetch_json(page, REPLIES_PATH, params)

    def _page_fetch_json(self, page: "Page", path: str, params: dict[str, str]) -> dict:
        url = f"https://www.douyin.com{path}"
        max_attempts = max(1, self.settings.request_retry_max_attempts)
        request_timeout_ms = min(self.settings.playwright_timeout_ms, 15000)
        for attempt in range(1, max_attempts + 1):
            self._sleep_with_jitter()
            with self._request_slot():
                payload = page.evaluate(
                    """
                async ({ url, params, fallbackWebid, requestTimeoutMs }) => {
                  const xmst = window.localStorage.getItem('xmst');
                  const sysInfo = window.localStorage.getItem('SysInfo');
                  const tea6383 = window.localStorage.getItem('__tea_cache_tokens_6383');
                  const tea2285 = window.localStorage.getItem('__tea_cache_tokens_2285');
                  const tea3722 = window.localStorage.getItem('__tea_cache_tokens_3722');
                  let resolvedWebid = fallbackWebid;
                  try {
                    const sysInfoJson = sysInfo ? JSON.parse(sysInfo) : null;
                    resolvedWebid = sysInfoJson?.webid || resolvedWebid;
                  } catch (error) {}
                  if (!resolvedWebid) {
                    try {
                      const teaJson = tea6383 ? JSON.parse(tea6383) : null;
                      resolvedWebid = teaJson?.user_unique_id || teaJson?.web_id || resolvedWebid;
                    } catch (error) {}
                  }
                  if (!resolvedWebid) {
                    try {
                      const teaJson = tea2285 ? JSON.parse(tea2285) : null;
                      resolvedWebid = teaJson?.user_unique_id || teaJson?.web_id || resolvedWebid;
                    } catch (error) {}
                  }
                  if (!resolvedWebid) {
                    try {
                      const teaJson = tea3722 ? JSON.parse(tea3722) : null;
                      resolvedWebid = teaJson?.user_unique_id || teaJson?.web_id || resolvedWebid;
                    } catch (error) {}
                  }
                  if (!resolvedWebid) {
                    const svWebId = document.cookie
                      .split(';')
                      .map((item) => item.trim())
                      .find((item) => item.startsWith('s_v_web_id='));
                    if (svWebId) {
                      resolvedWebid = decodeURIComponent(svWebId.split('=').slice(1).join('='));
                    }
                  }
                  const finalParams = new URLSearchParams({
                    ...params,
                    device_platform: 'webapp',
                    aid: '6383',
                    channel: 'channel_pc_web',
                    version_code: '190600',
                    version_name: '19.6.0',
                    update_version_code: '170400',
                    pc_client_type: '1',
                    cookie_enabled: 'true',
                    browser_language: navigator.language || 'zh-CN',
                    browser_platform: navigator.platform || 'MacIntel',
                    browser_name: 'Chrome',
                    browser_version: '125.0.0.0',
                    browser_online: navigator.onLine ? 'true' : 'false',
                    engine_name: 'Blink',
                    os_name: 'Mac OS',
                    os_version: '10.15.7',
                    cpu_core_num: '8',
                    device_memory: '8',
                    engine_version: '109.0',
                    platform: 'PC',
                    screen_width: String(window.screen.width || 2560),
                    screen_height: String(window.screen.height || 1440),
                    effective_type: '4g',
                    round_trip_time: '50',
                    webid: resolvedWebid,
                    msToken: xmst || '',
                  });
                  const controller = new AbortController();
                  const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs);
                  let response;
                  try {
                    response = await fetch(`${url}?${finalParams.toString()}`, {
                      credentials: 'include',
                      signal: controller.signal,
                    });
                  } catch (error) {
                    if (error?.name === 'AbortError') {
                      return {
                        __request_timeout__: true,
                        status_msg: `fetch timed out after ${requestTimeoutMs}ms`,
                      };
                    }
                    throw error;
                  } finally {
                    window.clearTimeout(timeoutId);
                  }
                  const text = await response.text();
                  if (!text) {
                    return {};
                  }
                  try {
                    return JSON.parse(text);
                  } catch (error) {
                    return {
                      __invalid_json__: true,
                      status_code: response.status,
                      status_msg: text.slice(0, 512),
                    };
                  }
                }
                    """,
                    {
                        "url": url,
                        "params": params,
                        "fallbackWebid": _fallback_webid(),
                        "requestTimeoutMs": request_timeout_ms,
                    },
                )
            if not isinstance(payload, dict):
                raise ValueError(f"unexpected payload type from {path}: {type(payload)!r}")
            if self.settings.anti_crawl_detection_enabled and _is_anti_crawl_payload(payload):
                raise AntiCrawlDetectedError(
                    "anti-crawl payload detected in page fetch",
                    path=path,
                    marker=params.get("offset") or params.get("cursor"),
                )
            if payload.get("__request_timeout__"):
                if attempt < max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                raise TimeoutError(payload.get("status_msg") or f"request timed out for {path}")
            if payload.get("__invalid_json__"):
                if attempt < max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                return {}
            return payload
        return {}

    def _open_comment_panel(self, page: "Page") -> None:
        candidates = [
            ("评论", False),
            ("全部评论", False),
            ("留下你的精彩评论吧", False),
        ]
        for text, exact in candidates:
            try:
                locator = page.get_by_text(text, exact=exact)
                if locator.count() > 0:
                    locator.first.click(timeout=3000)
                    page.wait_for_timeout(2500)
            except Exception:
                continue
        try:
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(2500)
        except Exception:
            return

    def _search_via_state(
        self,
        query: str,
        cursor: str | None,
        limit: int | None,
        state_path: str,
    ) -> tuple[list[dict], str | None]:
        runtime = _load_state_runtime(state_path, self.settings.playwright_user_agent or "")
        results: list[dict] = []
        seen_ids: set[str] = set()
        offset = int(cursor or "0")
        search_id = ""
        max_pages = max(0, self.settings.search_state_max_pages)
        pages = 0
        while True:
            if max_pages > 0 and pages >= max_pages:
                break
            pages += 1
            payload = self._state_get_json(
                path=SEARCH_PATH,
                params={
                    "search_channel": "aweme_general",
                    "enable_history": "1",
                    "keyword": query,
                    "search_source": "tab_search",
                    "query_correct_type": "1",
                    "is_filter_search": "0",
                    "from_group_id": "7378810571505847586",
                    "offset": str(offset),
                    "count": str(SEARCH_COUNT),
                    "need_filter_settings": "1",
                    "list_type": "multi",
                    "search_id": search_id,
                },
                referer=f"https://www.douyin.com/search/{quote(query)}?aid=f594bbd9-a0e2-4651-9319-ebe3cb6298c1&type=general",
                runtime=runtime,
                signed=False,
            )
            page_items = 0
            for item in _normalize_search_payload(payload):
                aweme_id = str(item.get("aweme_id") or item.get("video_id") or "")
                if not aweme_id or aweme_id in seen_ids:
                    continue
                seen_ids.add(aweme_id)
                results.append(item)
                page_items += 1
                if limit and len(results) >= limit:
                    return results[:limit], _next_cursor(payload)
            search_id = str((payload.get("extra") or {}).get("logid") or search_id)
            next_cursor = _next_cursor(payload)
            if not next_cursor or page_items == 0:
                break
            try:
                next_offset = int(next_cursor)
            except ValueError:
                break
            if next_offset == offset:
                break
            offset = next_offset
        return results[:limit] if limit else results, None

    def _comments_via_state(
        self,
        platform_video_id: str,
        cursor: str | None,
        state_path: str,
    ) -> tuple[list[dict], str | None]:
        runtime = _load_state_runtime(state_path, self.settings.playwright_user_agent or "")
        payload = self._state_get_json(
            path=COMMENTS_PATH,
            params={
                "aweme_id": platform_video_id,
                "cursor": cursor or "0",
                "count": str(COMMENTS_COUNT),
                "item_type": "0",
            },
            referer=f"https://www.douyin.com/video/{platform_video_id}",
            runtime=runtime,
            signed=True,
        )
        return _normalize_comment_payload(payload), _next_cursor(payload)

    def _replies_via_state(
        self,
        platform_video_id: str,
        root_comment_platform_id: str,
        cursor: str | None,
        state_path: str,
    ) -> tuple[list[dict], str | None]:
        runtime = _load_state_runtime(state_path, self.settings.playwright_user_agent or "")
        payload = self._state_get_json(
            path=REPLIES_PATH,
            params={
                "comment_id": root_comment_platform_id,
                "cursor": cursor or "0",
                "count": str(COMMENTS_COUNT),
                "item_type": "0",
                "item_id": platform_video_id,
            },
            referer=f"https://www.douyin.com/video/{platform_video_id}",
            runtime=runtime,
            signed=True,
        )
        replies = _normalize_comment_payload(payload)
        self._reply_cache[(Platform.DOUYIN, platform_video_id, root_comment_platform_id)] = replies
        return replies, _next_cursor(payload)

    def _state_get_json(
        self,
        path: str,
        params: dict[str, str],
        referer: str,
        runtime: _StateRuntime,
        signed: bool,
    ) -> dict:
        final_params = {
            **params,
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "MacIntel",
            "browser_name": "Chrome",
            "browser_version": "125.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Mac OS",
            "os_version": "10.15.7",
            "cpu_core_num": "8",
            "device_memory": "8",
            "engine_version": "109.0",
            "platform": "PC",
            "screen_width": "2560",
            "screen_height": "1440",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": runtime.webid,
            "msToken": runtime.xmst,
        }
        if signed:
            query = urlencode(final_params)
            final_params["a_bogus"] = self._sign_query(path, query, runtime.user_agent)
        headers = {
            "User-Agent": runtime.user_agent,
            "Cookie": runtime.cookie_header,
            "Host": "www.douyin.com",
            "Origin": "https://www.douyin.com/",
            "Referer": referer,
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
        }
        max_attempts = max(1, self.settings.request_retry_max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._sleep_with_jitter()
            try:
                with self._request_slot():
                    response = httpx.get(
                        f"https://www.douyin.com{path}",
                        params=final_params,
                        headers=headers,
                        timeout=30,
                        follow_redirects=True,
                        trust_env=False,
                    )
                if (
                    self.settings.anti_crawl_detection_enabled
                    and response.status_code in {403, 429}
                ):
                    raise AntiCrawlDetectedError(
                        f"anti-crawl http status {response.status_code}",
                        path=path,
                        status_code=response.status_code,
                        marker=params.get("offset") or params.get("cursor"),
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                response.raise_for_status()
                if not response.text:
                    return {}
                payload = response.json()
                if self.settings.anti_crawl_detection_enabled and _is_anti_crawl_payload(payload):
                    raise AntiCrawlDetectedError(
                        "anti-crawl payload detected in state request",
                        path=path,
                        status_code=response.status_code,
                        marker=params.get("offset") or params.get("cursor"),
                    )
                return payload
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("request failed without response")

    def _sign_query(self, path: str, query: str, user_agent: str) -> str:
        signer = "sign_reply" if "/reply/" in path else "sign_datail"
        sign_script = _resolve_sign_script()
        command = (
            "const fs=require('fs');"
            f"const code=fs.readFileSync({json.dumps(str(sign_script))},'utf8');"
            "eval(code);"
            f"console.log({signer}({json.dumps(query)}, {json.dumps(user_agent)}));"
        )
        return subprocess.check_output(["node", "-e", command], text=True).strip()

    def _session(self, crawl_context: CrawlContext | None):
        class _SessionManager:
            def __init__(self, outer: "PlaywrightProviderClient", context: CrawlContext | None):
                self.outer = outer
                self.context = context
                self.session: _BrowserSession | None = None

            def __enter__(self) -> _BrowserSession:
                self.session = self.outer._open_session(self.context)
                return self.session

            def __exit__(self, exc_type, exc, tb) -> None:
                if self.session is not None:
                    self.session.close()

        return _SessionManager(self, crawl_context)

    def _open_session(self, crawl_context: CrawlContext | None) -> _BrowserSession:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        launch_kwargs = {
            "headless": self.settings.playwright_headless,
            "proxy": _parse_proxy_config(crawl_context.proxy_url if crawl_context else None),
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self.settings.playwright_channel:
            launch_kwargs["channel"] = self.settings.playwright_channel
        browser = playwright.chromium.launch(**launch_kwargs)
        context_kwargs = {
            "ignore_https_errors": True,
            "locale": self.settings.playwright_locale,
            "viewport": {"width": 1536, "height": 864},
        }
        if self.settings.playwright_timezone_id:
            context_kwargs["timezone_id"] = self.settings.playwright_timezone_id
        if self.settings.playwright_user_agent:
            context_kwargs["user_agent"] = self.settings.playwright_user_agent
        state_path = None
        if crawl_context and crawl_context.login_state_path:
            candidate = Path(crawl_context.login_state_path).expanduser()
            if not candidate.exists():
                raise FileNotFoundError(f"login state file not found: {candidate}")
            state_path = str(candidate)
        if state_path:
            context_kwargs["storage_state"] = state_path
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(self.settings.playwright_timeout_ms)
        self._prepare_page(page)
        return _BrowserSession(playwright=playwright, browser=browser, context=context, page=page)

    def _prepare_page(self, page: "Page") -> None:
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """
        )
        page.on("dialog", lambda dialog: dialog.dismiss())
