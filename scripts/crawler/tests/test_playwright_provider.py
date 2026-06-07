import json
from contextlib import contextmanager
from types import SimpleNamespace

from app.platforms.playwright_provider import (
    _CapturedResponse,
    PlaywrightProviderClient,
    _extract_webid,
    _is_missing_sign_script,
    _next_cursor,
    _parse_chunked_json_payload,
    _normalize_comment_payload,
    _normalize_search_payload,
)
from app.platforms.schemas import CrawlContext
from app.core.enums import Platform


class DummyPage:
    def __init__(self):
        self.url = ""

    def goto(self, *args, **kwargs):
        if args:
            self.url = args[0]
        return None

    def wait_for_timeout(self, *args, **kwargs):
        return None


class EvalPage(DummyPage):
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def evaluate(self, *args, **kwargs):
        self.calls += 1
        if not self.payloads:
            raise AssertionError("unexpected evaluate call")
        return self.payloads.pop(0)


class TimeoutPage(DummyPage):
    def __init__(self, url="", update_url_on_timeout=True):
        super().__init__()
        self.url = url
        self.update_url_on_timeout = update_url_on_timeout
        self.goto_calls = []

    def goto(self, *args, **kwargs):
        self.goto_calls.append((args, kwargs))
        if args and self.update_url_on_timeout:
            self.url = args[0]
        raise RuntimeError("Page.goto: Timeout 30000ms exceeded.")


def test_normalize_search_payload_handles_aweme_info_and_mix_items():
    payload = {
        "data": [
            {"aweme_info": {"aweme_id": "1", "desc": "first"}},
            {"aweme_mix_info": {"mix_items": [{"aweme_id": "2", "desc": "second"}]}},
            {"aweme_mix_info": {"mix_items": []}},
        ]
    }

    result = _normalize_search_payload(payload)

    assert [item["aweme_id"] for item in result] == ["1", "2"]


def test_normalize_comment_payload_filters_invalid_rows():
    payload = {
        "comments": [
            {"cid": "c1", "text": "hello"},
            {"comment_id": "c2", "text": "world"},
            {"text": "skip"},
        ]
    }

    result = _normalize_comment_payload(payload)

    assert [item.get("cid") or item.get("comment_id") for item in result] == ["c1", "c2"]


def test_parse_chunked_json_payload_extracts_json_object():
    payload = {"status_code": 0, "data": [{"aweme_info": {"aweme_id": "1"}}]}
    text = "1a\r\n" + json.dumps(payload, ensure_ascii=False) + "\r\n0\r\n\r\n"

    class DummyResponse:
        def text(self):
            return text

    result = _parse_chunked_json_payload(DummyResponse())

    assert result == payload


def test_next_cursor_returns_string_when_has_more():
    assert _next_cursor({"has_more": 1, "cursor": 15}) == "15"


def test_next_cursor_returns_none_without_more_pages():
    assert _next_cursor({"has_more": 0, "cursor": 20}) is None


def test_extract_webid_prefers_sysinfo():
    value = _extract_webid({"SysInfo": json.dumps({"webid": "7618119451833304585"})})

    assert value == "7618119451833304585"


def test_extract_webid_falls_back_to_cached_tokens():
    value = _extract_webid({"__tea_cache_tokens_6383": json.dumps({"user_unique_id": "123456"})})

    assert value == "123456"


def test_is_missing_sign_script_matches_expected_error():
    assert _is_missing_sign_script(FileNotFoundError("douyin sign script not found")) is True
    assert _is_missing_sign_script(FileNotFoundError("other missing file")) is False


def test_comments_falls_back_to_page_when_sign_script_missing(monkeypatch):
    client = PlaywrightProviderClient()

    def _raise(*args, **kwargs):
        raise FileNotFoundError("douyin sign script not found")

    @contextmanager
    def _fake_session(_crawl_context):
        yield SimpleNamespace(page=DummyPage())

    monkeypatch.setattr(client, "_comments_via_state", _raise)
    monkeypatch.setattr(client, "_session", _fake_session)
    monkeypatch.setattr(
        client,
        "_fetch_comment_payload",
        lambda page, platform_video_id, cursor: {
            "comments": [{"cid": "c1", "text": "hello"}],
            "has_more": 0,
            "cursor": 0,
        },
    )

    payload, cursor = client.comments(
        platform=Platform.DOUYIN,
        platform_video_id="video-1",
        cursor=None,
        crawl_context=CrawlContext(login_state_path="playwright_states/douyin_main.json"),
    )

    assert payload == [{"cid": "c1", "text": "hello"}]
    assert cursor is None


def test_comments_falls_back_to_ui_when_page_fetch_returns_empty(monkeypatch):
    client = PlaywrightProviderClient()

    @contextmanager
    def _fake_session(_crawl_context):
        yield SimpleNamespace(page=DummyPage())

    monkeypatch.setattr(client, "_session", _fake_session)
    monkeypatch.setattr(
        client,
        "_fetch_comment_payload",
        lambda page, platform_video_id, cursor: {"comments": [], "has_more": 0, "cursor": 0},
    )
    monkeypatch.setattr(
        client,
        "_fetch_comment_payload_via_ui",
        lambda page, platform_video_id: {
            "comments": [{"cid": "c-ui", "text": "from-ui"}],
            "has_more": 0,
            "cursor": 0,
        },
    )

    payload, cursor = client.comments(
        platform=Platform.DOUYIN,
        platform_video_id="video-ui",
        cursor=None,
        crawl_context=None,
    )

    assert payload == [{"cid": "c-ui", "text": "from-ui"}]
    assert cursor is None


def test_replies_falls_back_to_page_when_sign_script_missing(monkeypatch):
    client = PlaywrightProviderClient()

    def _raise(*args, **kwargs):
        raise FileNotFoundError("douyin sign script not found")

    @contextmanager
    def _fake_session(_crawl_context):
        yield SimpleNamespace(page=DummyPage())

    monkeypatch.setattr(client, "_replies_via_state", _raise)
    monkeypatch.setattr(client, "_session", _fake_session)
    monkeypatch.setattr(
        client,
        "_fetch_reply_payload",
        lambda page, platform_video_id, root_comment_platform_id, cursor: {
            "comments": [{"cid": "r1", "text": "reply"}],
            "has_more": 0,
            "cursor": 0,
        },
    )

    payload, cursor = client.replies(
        platform=Platform.DOUYIN,
        platform_video_id="video-1",
        root_comment_platform_id="root-1",
        cursor=None,
        crawl_context=CrawlContext(login_state_path="playwright_states/douyin_main.json"),
    )

    assert payload == [{"cid": "r1", "text": "reply"}]
    assert cursor is None


def test_page_fetch_json_retries_invalid_json_payload(monkeypatch):
    client = PlaywrightProviderClient()
    monkeypatch.setattr(client.settings, "request_retry_max_attempts", 2)
    monkeypatch.setattr(client, "_sleep_with_jitter", lambda: None)
    monkeypatch.setattr(client, "_sleep_with_backoff", lambda attempt: None)
    page = EvalPage(
        [
            {"__invalid_json__": True, "status_code": 200, "status_msg": ""},
            {"comments": [{"cid": "c1", "text": "ok"}], "has_more": 0, "cursor": 0},
        ]
    )

    payload = client._page_fetch_json(page, "/aweme/v1/web/comment/list/", {"cursor": "0"})

    assert payload == {"comments": [{"cid": "c1", "text": "ok"}], "has_more": 0, "cursor": 0}
    assert page.calls == 2


def test_page_fetch_json_returns_empty_after_exhausting_invalid_json(monkeypatch):
    client = PlaywrightProviderClient()
    monkeypatch.setattr(client.settings, "request_retry_max_attempts", 2)
    monkeypatch.setattr(client, "_sleep_with_jitter", lambda: None)
    monkeypatch.setattr(client, "_sleep_with_backoff", lambda attempt: None)
    page = EvalPage(
        [
            {"__invalid_json__": True, "status_code": 200, "status_msg": ""},
            {"__invalid_json__": True, "status_code": 200, "status_msg": ""},
        ]
    )

    payload = client._page_fetch_json(page, "/aweme/v1/web/comment/list/", {"cursor": "0"})

    assert payload == {}
    assert page.calls == 2


def test_page_fetch_json_raises_timeout_after_exhausting_request_timeouts(monkeypatch):
    client = PlaywrightProviderClient()
    monkeypatch.setattr(client.settings, "request_retry_max_attempts", 2)
    monkeypatch.setattr(client, "_sleep_with_jitter", lambda: None)
    monkeypatch.setattr(client, "_sleep_with_backoff", lambda attempt: None)
    page = EvalPage(
        [
            {"__request_timeout__": True, "status_msg": "fetch timed out after 15000ms"},
            {"__request_timeout__": True, "status_msg": "fetch timed out after 15000ms"},
        ]
    )

    try:
        client._page_fetch_json(page, "/aweme/v1/web/comment/list/", {"cursor": "0"})
    except TimeoutError as exc:
        assert str(exc) == "fetch timed out after 15000ms"
    else:
        raise AssertionError("expected timeout to be raised")
    assert page.calls == 2


def test_goto_video_page_uses_commit_navigation():
    client = PlaywrightProviderClient()
    page = DummyPage()

    client._goto_video_page(page, "video-1")

    assert page.url == "https://www.douyin.com/video/video-1"


def test_goto_video_page_tolerates_timeout_after_url_changes():
    client = PlaywrightProviderClient()
    page = TimeoutPage()

    client._goto_video_page(page, "video-1")

    assert page.url == "https://www.douyin.com/video/video-1"


def test_goto_video_page_raises_timeout_when_url_never_changes():
    client = PlaywrightProviderClient()
    page = TimeoutPage(url="https://www.douyin.com/", update_url_on_timeout=False)

    try:
        client._goto_video_page(page, "video-1")
    except RuntimeError as exc:
        assert str(exc) == "Page.goto: Timeout 30000ms exceeded."
    else:
        raise AssertionError("expected timeout to be raised")
