from __future__ import annotations

from typing import Callable, Mapping

from sensex_chain.socket import DataFeedError, FyersDataFeed


class FakeDataSocket:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.subscriptions: list[tuple[list[str], str]] = []
        self.connect_called = False
        self.close_called = False

    def subscribe(self, *, symbols: list[str], data_type: str) -> None:
        self.subscriptions.append((symbols, data_type))

    def connect(self) -> None:
        self.connect_called = True
        callback = self.kwargs["on_connect"]
        assert callable(callback)
        callback()

    def close_connection(self) -> None:
        self.close_called = True


def test_socket_subscribes_only_in_symbol_update_mode() -> None:
    created: list[FakeDataSocket] = []

    def factory(**kwargs: object) -> FakeDataSocket:
        socket = FakeDataSocket(**kwargs)
        created.append(socket)
        return socket

    received: list[Mapping[str, object]] = []
    feed = FyersDataFeed("app:token", socket_factory=factory)
    feed.start(["BSE:SENSEX-INDEX", "BSE:SENSEX26AUG80000CE"], received.append)

    assert created[0].subscriptions == [(["BSE:SENSEX-INDEX", "BSE:SENSEX26AUG80000CE"], "SymbolUpdate")]
    assert created[0].connect_called is True
    feed.stop()
    assert created[0].close_called is True


def test_socket_start_failure_has_a_safe_diagnostic_code() -> None:
    def failing_factory(**kwargs: object):
        raise RuntimeError("access token must not leak")

    feed = FyersDataFeed("app:token", socket_factory=failing_factory)

    with __import__("pytest").raises(DataFeedError) as error:
        feed.start(["BSE:SENSEX-INDEX"], lambda tick: None)

    assert str(error.value) == "SOCKET_START_FAILED"


def test_socket_does_not_close_before_the_sdk_reports_subscription_ready() -> None:
    created: list[FakeDataSocket] = []

    class UnreadySocket(FakeDataSocket):
        def connect(self) -> None:
            self.connect_called = True

    def factory(**kwargs: object) -> UnreadySocket:
        socket = UnreadySocket(**kwargs)
        created.append(socket)
        return socket

    feed = FyersDataFeed("app:token", socket_factory=factory)
    feed.start(["BSE:SENSEX-INDEX"], lambda tick: None)
    feed.stop()

    assert created[0].close_called is False


def test_socket_marks_a_closed_connection_as_not_live() -> None:
    created: list[FakeDataSocket] = []

    def factory(**kwargs: object) -> FakeDataSocket:
        socket = FakeDataSocket(**kwargs)
        created.append(socket)
        return socket

    feed = FyersDataFeed("app:token", socket_factory=factory)
    feed.start(["BSE:SENSEX-INDEX"], lambda tick: None)
    closed = created[0].kwargs["on_close"]
    assert callable(closed)
    closed({"reason": "connection closed"})

    assert feed.diagnostic_code == "SOCKET_CLOSED"
