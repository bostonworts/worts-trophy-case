from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class RateLimitEntry:
    count: int
    reset_at: datetime


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self.entries: dict[str, RateLimitEntry] = {}

    def hit(self, key: str, *, now: datetime | None = None) -> int | None:
        now = now or datetime.now(UTC)
        entry = self.entries.get(key)
        if entry is None or entry.reset_at <= now:
            self.entries[key] = RateLimitEntry(count=1, reset_at=now + self.window)
            return None

        if entry.count >= self.limit:
            return max(1, int((entry.reset_at - now).total_seconds()))

        entry.count += 1
        return None

    def reset(self, key: str) -> None:
        self.entries.pop(key, None)

    def clear(self) -> None:
        self.entries.clear()
