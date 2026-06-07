from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class CircuitState:
    failure_count: int
    cooldown_until: datetime | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def apply_failure(
    failure_count: int,
    threshold: int,
    cooldown_seconds: int,
) -> CircuitState:
    updated = failure_count + 1
    if updated >= threshold:
        return CircuitState(
            failure_count=updated,
            cooldown_until=datetime.now(UTC) + timedelta(seconds=cooldown_seconds),
        )
    return CircuitState(failure_count=updated, cooldown_until=None)


def reset_failures() -> CircuitState:
    return CircuitState(failure_count=0, cooldown_until=None)


def is_available(cooldown_until: datetime | None) -> bool:
    if cooldown_until is None:
        return True
    return datetime.now(UTC) >= _as_utc(cooldown_until)
