"""Small adapter around FYERS API v3 DataSocket only."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol


class DataFeedError(RuntimeError):
    """Raised with a safe diagnostic code when the market-data socket cannot start."""


class DataSocket(Protocol):
    def subscribe(self, *, symbols: list[str], data_type: str) -> None: ...

    def connect(self) -> None: ...

    def close_connection(self) -> None: ...


SocketFactory = Callable[..., DataSocket]


class FyersDataFeed:
    """Owns one FYERS DataSocket and exposes only symbol-update ticks."""

    def __init__(self, access_token: str, socket_factory: SocketFactory | None = None) -> None:
        self._access_token = access_token
        self._socket_factory = socket_factory or _sdk_socket_factory
        self._socket: DataSocket | None = None
        self._diagnostic_code = "SOCKET_NOT_STARTED"

    @property
    def diagnostic_code(self) -> str:
        return self._diagnostic_code

    def start(self, symbols: Sequence[str], on_tick: Callable[[Mapping[str, object]], None]) -> None:
        requested_symbols = list(symbols)

        def on_connect() -> None:
            assert self._socket is not None
            self._socket.subscribe(symbols=requested_symbols, data_type="SymbolUpdate")
            self._diagnostic_code = "SOCKET_SUBSCRIBED"

        def on_message(message: Any) -> None:
            if isinstance(message, Mapping):
                on_tick(message)

        def on_error(_message: Any) -> None:
            self._diagnostic_code = "SOCKET_RUNTIME_ERROR"

        try:
            self._socket = self._socket_factory(access_token=self._access_token, on_connect=on_connect, on_message=on_message, on_error=on_error, on_close=lambda _message: None, litemode=False, write_to_file=False, reconnect=True)
            self._socket.connect()
        except Exception as exc:
            self._socket = None
            self._diagnostic_code = "SOCKET_START_FAILED"
            raise DataFeedError("SOCKET_START_FAILED") from exc

    def stop(self) -> None:
        if self._socket is not None:
            self._socket.close_connection()
            self._socket = None


def _sdk_socket_factory(**kwargs: object) -> DataSocket:
    from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket

    return FyersDataSocket(**kwargs)
