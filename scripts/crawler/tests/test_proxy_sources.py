from app.services.proxy_sources import ProxySourceService


class DummyProxyService:
    def __init__(self):
        self.items: list[tuple[str, str]] = []

    def import_proxy(self, label: str, proxy_url: str):
        self.items.append((label, proxy_url))
        return None


def test_import_from_source_normalizes_and_limits(monkeypatch):
    service = ProxySourceService(DummyProxyService())

    class DummyResponse:
        text = "1.1.1.1:80\n1.1.1.1:80\n# comment\n2.2.2.2:8080\n"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("app.services.proxy_sources.httpx.get", lambda *args, **kwargs: DummyResponse())
    created = service.import_from_source("the_speedx_http", limit=2)

    assert created == 2
    assert service.proxy_service.items == [
        ("the_speedx_http_http_1_1_1_1_80", "http://1.1.1.1:80"),
        ("the_speedx_http_http_2_2_2_2_8080", "http://2.2.2.2:8080"),
    ]


def test_import_from_ipproxypool_normalizes_list_payload(monkeypatch):
    service = ProxySourceService(DummyProxyService())

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [["3.3.3.3", 8080, 10], ["4.4.4.4", 9000, 8]]

    monkeypatch.setattr("app.services.proxy_sources.httpx.get", lambda *args, **kwargs: DummyResponse())
    created = service.import_from_ipproxypool(
        limit=2,
        base_url="http://127.0.0.1:8000",
        types=0,
        protocol=0,
        country="国内",
    )

    assert created == 2
    assert service.proxy_service.items == [
        ("ipproxypool_api_http_3_3_3_3_8080", "http://3.3.3.3:8080"),
        ("ipproxypool_api_http_4_4_4_4_9000", "http://4.4.4.4:9000"),
    ]


def test_import_from_ipproxypool_supports_dict_payload(monkeypatch):
    service = ProxySourceService(DummyProxyService())

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"ip": "5.5.5.5", "port": 443}]}

    monkeypatch.setattr("app.services.proxy_sources.httpx.get", lambda *args, **kwargs: DummyResponse())
    created = service.import_from_ipproxypool(
        limit=1,
        base_url="http://127.0.0.1:8000",
        protocol=1,
    )

    assert created == 1
    assert service.proxy_service.items == [
        ("ipproxypool_api_https_5_5_5_5_443", "https://5.5.5.5:443")
    ]
