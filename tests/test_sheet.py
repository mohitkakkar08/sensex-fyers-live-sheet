from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sensex_chain.cache import ChainRow, ChainSnapshot, MarketTick
from sensex_chain.sheet import CHAIN_HEADERS, GoogleSheetGateway, WorkerStatus
from sensex_chain.timebox import KOLKATA


class FakeRequest:
    def __init__(self, callback) -> None:
        self._callback = callback

    def execute(self) -> None:
        self._callback()


class FakeReadRequest:
    def __init__(self, values: list[list[object]]) -> None:
        self._values = values

    def execute(self) -> dict[str, list[list[object]]]:
        return {"values": self._values}


class FakeValues:
    def __init__(self, parent) -> None:
        self.parent = parent

    def batchUpdate(self, *, spreadsheetId: str, body: dict[str, object]) -> FakeRequest:
        def save() -> None:
            self.parent.values_batch_updates += 1
            self.parent.last_sheet_id = spreadsheetId
            self.parent.last_body = body

        return FakeRequest(save)

    def get(self, *, spreadsheetId: str, range: str) -> FakeReadRequest:
        assert spreadsheetId == self.parent.expected_sheet_id
        assert range == "SENSEX!R7:R500"
        return FakeReadRequest(self.parent.existing_strikes)


class FakeSpreadsheets:
    def __init__(self, parent) -> None:
        self.parent = parent

    def values(self) -> FakeValues:
        return FakeValues(self.parent)


class FakeSheetsService:
    def __init__(self, existing_strikes: list[list[object]] | None = None) -> None:
        self.values_batch_updates = 0
        self.last_sheet_id = ""
        self.last_body: dict[str, object] = {}
        self.expected_sheet_id = "sheet-id"
        self.existing_strikes = existing_strikes or []

    def spreadsheets(self) -> FakeSpreadsheets:
        return FakeSpreadsheets(self)


def snapshot() -> ChainSnapshot:
    now = datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)
    return ChainSnapshot(
        expiry=date(2026, 8, 6),
        updated_at=now,
        underlying=MarketTick("BSE:SENSEX-INDEX", ltp=80050.0, prev_close=80000.0),
        india_vix=MarketTick("NSE:INDIAVIX-INDEX", ltp=14.5, prev_close=14.0),
        rows=(
            ChainRow(
                strike=Decimal("80000"),
                call=MarketTick("BSE:SENSEX26AUG80000CE", ltp=125.0, oi=400.0),
                put=MarketTick("BSE:SENSEX26AUG80000PE"),
            ),
        ),
    )


def test_write_snapshot_uses_one_values_batch_update() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    assert service.values_batch_updates == 1
    assert service.last_sheet_id == "sheet-id"
    assert [item["range"] for item in service.last_body["data"]] == ["SENSEX!A1:AL4", "SENSEX!A6:AL7"]


def test_chain_layout_matches_the_full_ce_strike_pe_display() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    chain_rows = service.last_body["data"][1]["values"]
    assert len(CHAIN_HEADERS) == 38
    assert chain_rows[0] == CHAIN_HEADERS
    assert chain_rows[0][16] == "CE LTP"
    assert chain_rows[0][17] == "Strike"
    assert chain_rows[0][18] == "PE LTP"
    assert chain_rows[0][-2:] == ["CE VWAP", "PE VWAP"]


def test_chain_layout_places_live_fields_in_their_ce_and_pe_columns() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    row = service.last_body["data"][1]["values"][1]
    assert row[16] == 125.0  # CE LTP (column Q)
    assert row[17] == 80000.0  # Strike (column R)
    assert row[18] == ""  # PE LTP (column S)
    assert row[23] == ""  # PE OI (column X)


def test_chain_layout_writes_oi_and_greeks_in_their_named_columns() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")
    rich_snapshot = ChainSnapshot(
        expiry=date(2026, 8, 6),
        updated_at=datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA),
        underlying=MarketTick("BSE:SENSEX-INDEX", ltp=80050.0),
        india_vix=MarketTick("NSE:INDIAVIX-INDEX", ltp=14.5),
        rows=(
            ChainRow(
                strike=Decimal("80000"),
                call=MarketTick("BSE:SENSEX26AUG80000CE", oi=400.0, oi_change=25.0, iv=16.2, delta=0.51, gamma=0.001, theta=-12.3, vega=8.7, rho=1.2),
                put=MarketTick("BSE:SENSEX26AUG80000PE", oi=450.0, oi_change=-10.0, iv=17.1, delta=-0.49, gamma=0.002, theta=-11.8, vega=8.2, rho=-1.1),
            ),
        ),
    )

    gateway.write_snapshot(rich_snapshot, WorkerStatus.connected(rich_snapshot.updated_at))

    row = service.last_body["data"][1]["values"][1]
    assert row[4:10] == [1.2, -12.3, 8.7, 0.001, 0.51, 16.2]
    assert row[10:12] == [400.0, 25.0]
    assert row[22:31] == [-10.0, 450.0, -2.1739, 17.1, -0.49, 0.002, 8.2, -11.8, -1.1]

def test_missing_market_fields_are_written_as_blank_cells() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    chain_rows = service.last_body["data"][1]["values"]
    assert "" in chain_rows[1]


def test_summary_includes_live_india_vix() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    summary_rows = service.last_body["data"][0]["values"]
    assert summary_rows[2][0] == "NSE:INDIAVIX-INDEX"
    assert summary_rows[2][5] == 14.5


def test_summary_and_chain_timestamps_use_plain_ist_display_format() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    summary_rows = service.last_body["data"][0]["values"]
    chain_row = service.last_body["data"][1]["values"][1]
    assert summary_rows[3][11] == "04/08/2026 09:15:00 IST"
    assert chain_row[35] == "04/08/2026 09:15:00 IST"


def test_write_snapshot_clears_stale_option_rows_from_a_previous_expiry() -> None:
    service = FakeSheetsService(existing_strikes=[[80000], [80100]])
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    data = service.last_body["data"]
    assert data[2]["range"] == "SENSEX!A8:AL8"
    assert data[2]["values"] == [[""] * len(CHAIN_HEADERS)]
