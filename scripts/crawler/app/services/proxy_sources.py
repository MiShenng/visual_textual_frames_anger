from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.proxies import ProxyService


@dataclass(frozen=True, slots=True)
class ProxySource:
    name: str
    url: str
    scheme: str
    description: str


PROXY_SOURCES: tuple[ProxySource, ...] = (
    ProxySource(
        name="the_speedx_http",
        url="https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        scheme="http",
        description="TheSpeedX HTTP raw list",
    ),
    ProxySource(
        name="roosterkid_https",
        url="https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        scheme="http",
        description="roosterkid HTTPS raw list",
    ),
    ProxySource(
        name="monosans_http",
        url="https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        scheme="http",
        description="monosans HTTP raw list",
    ),
    ProxySource(
        name="monosans_socks5",
        url="https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        scheme="socks5",
        description="monosans SOCKS5 raw list",
    ),
)


def list_proxy_sources() -> list[ProxySource]:
    return list(PROXY_SOURCES)


class ProxySourceService:
    def __init__(self, proxy_service: ProxyService):
        self.proxy_service = proxy_service
        self.settings = get_settings()

    def import_from_source(self, source_name: str, limit: int | None = None) -> int:
        source = self._get_source(source_name)
        response = httpx.get(source.url, timeout=20, trust_env=False)
        response.raise_for_status()
        created = 0
        seen: set[str] = set()
        for raw_line in response.text.splitlines():
            proxy = self._normalize_proxy(source.scheme, raw_line)
            if not proxy or proxy in seen:
                continue
            seen.add(proxy)
            label = self._label_for(source.name, proxy)
            self.proxy_service.import_proxy(label, proxy)
            created += 1
            if limit is not None and created >= limit:
                break
        return created

    def import_from_ipproxypool(
        self,
        limit: int | None = None,
        *,
        base_url: str | None = None,
        types: int | None = None,
        protocol: int | None = None,
        country: str | None = None,
        area: str | None = None,
    ) -> int:
        resolved_base_url = (base_url or self.settings.ipproxypool_base_url).strip()
        if not resolved_base_url:
            raise ValueError("ipproxypool base url is not configured")

        resolved_limit = limit if limit is not None else 100
        resolved_types = self.settings.ipproxypool_types if types is None else types
        resolved_protocol = (
            self.settings.ipproxypool_protocol if protocol is None else protocol
        )
        resolved_country = (
            self.settings.ipproxypool_country if country is None else country
        )
        resolved_area = self.settings.ipproxypool_area if area is None else area

        params: dict[str, int | str] = {
            "count": resolved_limit,
            "types": resolved_types,
            "protocol": resolved_protocol,
        }
        if resolved_country:
            params["country"] = resolved_country
        if resolved_area:
            params["area"] = resolved_area

        response = httpx.get(
            f"{resolved_base_url.rstrip('/')}/",
            params=params,
            timeout=20,
            trust_env=False,
        )
        response.raise_for_status()

        created = 0
        seen: set[str] = set()
        scheme = self._scheme_for_protocol(resolved_protocol)
        for proxy in self._parse_ipproxypool_payload(response.json(), scheme):
            if proxy in seen:
                continue
            seen.add(proxy)
            label = self._label_for("ipproxypool_api", proxy)
            self.proxy_service.import_proxy(label, proxy)
            created += 1
            if limit is not None and created >= limit:
                break
        return created

    def _get_source(self, source_name: str) -> ProxySource:
        for source in PROXY_SOURCES:
            if source.name == source_name:
                return source
        raise ValueError(f"unknown proxy source: {source_name}")

    def _normalize_proxy(self, scheme: str, raw_line: str) -> str | None:
        text = raw_line.strip()
        if not text or text.startswith("#"):
            return None
        if "://" in text:
            return text
        if ":" not in text:
            return None
        return f"{scheme}://{text}"

    def _label_for(self, source_name: str, proxy_url: str) -> str:
        normalized = (
            proxy_url.replace("://", "_")
            .replace("@", "_")
            .replace(":", "_")
            .replace("/", "_")
            .replace(".", "_")
        )
        return f"{source_name}_{normalized}"

    def _scheme_for_protocol(self, protocol: int) -> str:
        if protocol == 1:
            return "https"
        return "http"

    def _parse_ipproxypool_payload(self, payload: object, scheme: str) -> list[str]:
        if isinstance(payload, dict):
            candidates = payload.get("data", [])
        else:
            candidates = payload
        if not isinstance(candidates, list):
            raise ValueError("unexpected ipproxypool payload")

        proxies: list[str] = []
        for item in candidates:
            proxy = self._normalize_ipproxypool_item(item, scheme)
            if proxy is not None:
                proxies.append(proxy)
        return proxies

    def _normalize_ipproxypool_item(self, item: object, scheme: str) -> str | None:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            host = str(item[0]).strip()
            port = str(item[1]).strip()
            if host and port:
                return f"{scheme}://{host}:{port}"
            return None
        if isinstance(item, dict):
            host = str(item.get("ip", "")).strip()
            port = str(item.get("port", "")).strip()
            if host and port:
                return f"{scheme}://{host}:{port}"
        return None
