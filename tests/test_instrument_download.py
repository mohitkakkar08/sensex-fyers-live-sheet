from __future__ import annotations

from sensex_chain.instruments import FyersInstrumentCatalog, INSTRUMENT_MASTER_URL


def test_download_uses_bse_master_url() -> None:
    class Response:
        text = "Symbol Ticker,Underlying Symbol,Expiry Date,Strike Price,Option Type\n"

        def raise_for_status(self) -> None:
            pass

    class Http:
        def __init__(self) -> None:
            self.url = ""

        def get(self, url: str, *, timeout: int) -> Response:
            self.url = url
            assert timeout == 30
            return Response()

    http = Http()
    FyersInstrumentCatalog.download(http)
    assert http.url == INSTRUMENT_MASTER_URL
