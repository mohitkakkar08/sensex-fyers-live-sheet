from __future__ import annotations

from sensex_chain.rate_limit import FyersRequestGate


def test_request_gate_enforces_a_minimum_interval_and_exponential_backoff() -> None:
    now = [0.0]
    gate = FyersRequestGate(monotonic=lambda: now[0], minimum_interval_seconds=1.0)

    assert gate.acquire().allowed is True
    assert gate.acquire().retry_in_seconds == 1
    now[0] = 1.0
    assert gate.acquire().allowed is True

    gate.on_rate_limit()
    assert gate.acquire().retry_in_seconds == 30
    now[0] = 31.0
    assert gate.acquire().allowed is True
    gate.on_rate_limit()
    assert gate.acquire().retry_in_seconds == 60


def test_request_gate_prefers_a_valid_server_retry_after() -> None:
    now = [10.0]
    gate = FyersRequestGate(monotonic=lambda: now[0])

    gate.on_rate_limit(retry_after_seconds=75)

    assert gate.acquire().retry_in_seconds == 75