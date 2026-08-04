"""Conservative in-process request gate for FYERS REST data calls."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from time import monotonic as system_monotonic
from typing import Callable


@dataclass(frozen=True)
class RequestPermission:
    allowed: bool
    retry_in_seconds: int = 0


class FyersRequestGate:
    """Avoid bursts and make a 429 pause later REST attempts without blocking sockets."""

    def __init__(self, monotonic: Callable[[], float] = system_monotonic, minimum_interval_seconds: float = 1.0, base_backoff_seconds: float = 30.0, maximum_backoff_seconds: float = 300.0) -> None:
        self._monotonic = monotonic
        self._minimum_interval_seconds = minimum_interval_seconds
        self._base_backoff_seconds = base_backoff_seconds
        self._maximum_backoff_seconds = maximum_backoff_seconds
        self._next_allowed_at = 0.0
        self._consecutive_rate_limits = 0

    def acquire(self) -> RequestPermission:
        now = self._monotonic()
        if now < self._next_allowed_at:
            return RequestPermission(False, ceil(self._next_allowed_at - now))
        self._next_allowed_at = now + self._minimum_interval_seconds
        return RequestPermission(True)

    def on_success(self) -> None:
        self._consecutive_rate_limits = 0

    def on_rate_limit(self, retry_after_seconds: float | None = None) -> int:
        self._consecutive_rate_limits += 1
        fallback = min(self._base_backoff_seconds * (2 ** (self._consecutive_rate_limits - 1)), self._maximum_backoff_seconds)
        delay = retry_after_seconds if retry_after_seconds is not None and retry_after_seconds > 0 else fallback
        self._next_allowed_at = max(self._next_allowed_at, self._monotonic() + delay)
        return ceil(delay)