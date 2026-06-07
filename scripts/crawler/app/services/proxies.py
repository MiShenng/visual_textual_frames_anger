from datetime import UTC, datetime
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import ProxyStatus
from app.services.circuit_breaker import apply_failure, is_available, reset_failures
from app.storage.models import ProxyEndpoint


class ProxyService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._rotation_cursor = 0

    def import_proxy(self, label: str, proxy_url: str) -> ProxyEndpoint:
        existing = self.db.scalar(select(ProxyEndpoint).where(ProxyEndpoint.label == label))
        if existing is not None:
            existing.proxy_url = proxy_url
            existing.status = ProxyStatus.ACTIVE
            existing.failure_count = 0
            existing.cooldown_until = None
            existing.last_checked_at = None
            existing.last_success_at = None
            self.db.commit()
            self.db.refresh(existing)
            return existing
        proxy = ProxyEndpoint(label=label, proxy_url=proxy_url)
        self.db.add(proxy)
        self.db.commit()
        self.db.refresh(proxy)
        return proxy

    def list_proxies(self) -> list[ProxyEndpoint]:
        return list(self.db.scalars(select(ProxyEndpoint).order_by(ProxyEndpoint.id.asc())))

    def infer_source(self, proxy: ProxyEndpoint) -> str:
        for prefix in (
            "the_speedx",
            "roosterkid",
            "monosans",
            "ipproxypool",
            "manual",
            "proxy",
        ):
            if proxy.label.startswith(prefix):
                return prefix
        return proxy.label.split("_", 1)[0]

    def validate_proxy(self, proxy: ProxyEndpoint) -> bool:
        scheme = urlparse(proxy.proxy_url).scheme.lower()
        if scheme in {"http", "https"}:
            try:
                response = httpx.get(
                    "http://httpbin.org/ip",
                    proxy=proxy.proxy_url,
                    timeout=5,
                    trust_env=False,
                )
                response.raise_for_status()
                self.mark_success(proxy)
                return True
            except Exception:
                self.mark_failure(proxy)
                return False

        host = urlparse(proxy.proxy_url).hostname
        port = urlparse(proxy.proxy_url).port
        if not host or not port:
            self.mark_failure(proxy)
            return False
        try:
            with socket.create_connection((host, port), timeout=3):
                self.mark_success(proxy)
                return True
        except OSError:
            self.mark_failure(proxy)
            return False

    def validate_proxies(self, limit: int | None = None) -> dict[str, int]:
        checked = 0
        passed = 0
        for proxy in self.list_proxies():
            if limit is not None and checked >= limit:
                break
            checked += 1
            if self.validate_proxy(proxy):
                passed += 1
        return {"checked": checked, "passed": passed, "failed": checked - passed}

    def cleanup_invalid_proxies(self) -> int:
        removed = 0
        for proxy in list(self.db.scalars(select(ProxyEndpoint))):
            if proxy.failure_count <= 0:
                continue
            if proxy.last_success_at is not None and proxy.status == ProxyStatus.ACTIVE:
                continue
            self.db.delete(proxy)
            removed += 1
        self.db.commit()
        return removed

    def acquire_proxy(self, exclude_labels: set[str] | None = None) -> ProxyEndpoint | None:
        excluded = exclude_labels or set()
        stmt = select(ProxyEndpoint).order_by(ProxyEndpoint.id.asc())
        candidates: list[ProxyEndpoint] = []
        for proxy in self.db.scalars(stmt):
            if proxy.status == ProxyStatus.DISABLED:
                continue
            if proxy.label in excluded:
                continue
            if is_available(proxy.cooldown_until):
                candidates.append(proxy)
        if not candidates:
            return None
        index = self._rotation_cursor % len(candidates)
        self._rotation_cursor = (self._rotation_cursor + 1) % len(candidates)
        selected = candidates[index]
        selected.status = ProxyStatus.ACTIVE
        self.db.commit()
        return selected

    def mark_success(self, proxy: ProxyEndpoint) -> None:
        state = reset_failures()
        proxy.failure_count = state.failure_count
        proxy.cooldown_until = state.cooldown_until
        proxy.status = ProxyStatus.ACTIVE
        proxy.last_success_at = datetime.now(UTC)
        proxy.last_checked_at = datetime.now(UTC)
        self.db.commit()

    def mark_failure(self, proxy: ProxyEndpoint) -> None:
        state = apply_failure(
            proxy.failure_count,
            threshold=self.settings.failure_threshold,
            cooldown_seconds=self.settings.cooldown_seconds,
        )
        proxy.failure_count = state.failure_count
        proxy.cooldown_until = state.cooldown_until
        proxy.status = ProxyStatus.COOLDOWN if state.cooldown_until else ProxyStatus.ACTIVE
        proxy.last_checked_at = datetime.now(UTC)
        self.db.commit()
