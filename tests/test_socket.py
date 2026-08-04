from __future__ import annotations

from typing import Callable, Mapping

from sensex_chain.socket import FyersDataFeed


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
